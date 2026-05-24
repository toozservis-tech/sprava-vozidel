import Foundation

final class APIClient: NetworkService {
    private static let defaultBaseURLString = "https://hub.toozservis.cz"
    private static let configurationStorageKey = "sprava_vozidel_api_base_url"
    private static let configurationEnvironmentKey = "SPRAVA_VOZIDEL_API_BASE_URL"

    private static let fallbackBaseURLStrings = [
        "https://hub.toozservis.cz",
        "http://127.0.0.1:8000"
    ]

    static func configuredBaseURLString() -> String {
        if let environmentOverride = ProcessInfo.processInfo.environment[configurationEnvironmentKey]?
            .trimmingCharacters(in: .whitespacesAndNewlines),
           !environmentOverride.isEmpty
        {
            return environmentOverride
        }

        if let infoOverride = Bundle.main.object(forInfoDictionaryKey: configurationEnvironmentKey) as? String {
            let trimmed = infoOverride.trimmingCharacters(in: .whitespacesAndNewlines)
            if !trimmed.isEmpty {
                return trimmed
            }
        }

        if let persistedOverride = UserDefaults.standard.string(forKey: configurationStorageKey)?
            .trimmingCharacters(in: .whitespacesAndNewlines),
           !persistedOverride.isEmpty
        {
            return persistedOverride
        }

        return defaultBaseURLString
    }

    static func setConfiguredBaseURLString(_ value: String) {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty {
            UserDefaults.standard.removeObject(forKey: configurationStorageKey)
        } else {
            UserDefaults.standard.set(trimmed, forKey: configurationStorageKey)
        }
    }

    private static func normalizedURL(from raw: String) -> URL? {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        if let direct = URL(string: trimmed), direct.scheme != nil {
            return direct
        }
        return URL(string: "https://\(trimmed)")
    }

    private static func candidateBaseURLs() -> [URL] {
        var candidates: [URL] = []
        if let configured = normalizedURL(from: configuredBaseURLString()) {
            candidates.append(configured)
        }
        for fallback in fallbackBaseURLStrings {
            if let url = normalizedURL(from: fallback), !candidates.contains(where: { $0.absoluteString == url.absoluteString }) {
                candidates.append(url)
            }
        }
        return candidates
    }

    private let baseURLProvider: () -> URL
    private let session: URLSession
    private let decoder: JSONDecoder
    private let encoder: JSONEncoder

    init(baseURL: URL? = nil, session: URLSession = .shared) {
        if let baseURL {
            self.baseURLProvider = { baseURL }
        } else {
            self.baseURLProvider = {
                APIClient.candidateBaseURLs().first ?? URL(string: APIClient.defaultBaseURLString)!
            }
        }
        self.session = session

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let value = try container.decode(String.self)

            let formats = [
                "yyyy-MM-dd'T'HH:mm:ss.SSSSSS",
                "yyyy-MM-dd'T'HH:mm:ss.SSS",
                "yyyy-MM-dd'T'HH:mm:ss",
                "yyyy-MM-dd"
            ]
            let formatter = DateFormatter()
            formatter.locale = Locale(identifier: "en_US_POSIX")
            formatter.timeZone = TimeZone(secondsFromGMT: 0)

            for format in formats {
                formatter.dateFormat = format
                if let parsed = formatter.date(from: value) {
                    return parsed
                }
            }

            if let isoDate = ISO8601DateFormatter().date(from: value) {
                return isoDate
            }

            throw DecodingError.dataCorruptedError(in: container, debugDescription: "Unsupported date format: \(value)")
        }
        self.decoder = decoder

        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        encoder.dateEncodingStrategy = .iso8601
        self.encoder = encoder
    }

    func request<T: Decodable>(_ endpoint: APIEndpoint, token: String?) async throws -> T {
        let request = try buildRequest(for: endpoint, token: token)
        do {
            let (data, response) = try await session.data(for: request)
            try validate(response: response, data: data)
            do {
                return try decoder.decode(T.self, from: data)
            } catch {
                if isLikelyCloudflareChallenge(data: data) {
                    throw APIError.serverError("Server vyžaduje bezpečnostní ověření (Cloudflare). Zkuste přihlášení znovu.")
                }
                let bodyPreview = String(data: data, encoding: .utf8)?
                    .trimmingCharacters(in: .whitespacesAndNewlines)
                    .prefix(180) ?? ""
                if !bodyPreview.isEmpty {
                    throw APIError.serverError("Neočekávaná odpověď serveru: \(bodyPreview)")
                }
                throw APIError.decodingError
            }
        } catch let error as APIError {
            throw error
        } catch {
            throw APIError.transportError(error.localizedDescription)
        }
    }

    func requestNoContent(_ endpoint: APIEndpoint, token: String?) async throws {
        let request = try buildRequest(for: endpoint, token: token)
        do {
            let (data, response) = try await session.data(for: request)
            try validate(response: response, data: data)
        } catch let error as APIError {
            throw error
        } catch {
            throw APIError.transportError(error.localizedDescription)
        }
    }

    func encodeBody<T: Encodable>(_ value: T) throws -> Data {
        try encoder.encode(value)
    }


    func requestData(_ endpoint: APIEndpoint, token: String?) async throws -> Data {
        let request = try buildRequest(for: endpoint, token: token)
        do {
            let (data, response) = try await session.data(for: request)
            try validate(response: response, data: data)
            return data
        } catch let error as APIError {
            throw error
        } catch {
            throw APIError.transportError(error.localizedDescription)
        }
    }

    private func buildRequest(for endpoint: APIEndpoint, token: String?) throws -> URLRequest {
        let baseURL = baseURLProvider()
        guard var components = URLComponents(url: mergedURL(baseURL: baseURL, endpointPath: endpoint.path), resolvingAgainstBaseURL: false) else {
            throw APIError.invalidURL
        }

        if !endpoint.queryItems.isEmpty {
            components.queryItems = endpoint.queryItems
        }

        guard let url = components.url else {
            throw APIError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = endpoint.method.rawValue
        request.timeoutInterval = endpoint.timeoutInterval ?? 20
        request.httpBody = endpoint.body
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if endpoint.body != nil {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        request.setValue("ios_app", forHTTPHeaderField: "X-Client-Platform")
        if let token, !token.isEmpty {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        return request
    }

    private func mergedURL(baseURL: URL, endpointPath: String) -> URL {
        var components = URLComponents(url: baseURL, resolvingAgainstBaseURL: false) ?? URLComponents()
        let basePath = components.path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        let endpoint = endpointPath.trimmingCharacters(in: CharacterSet(charactersIn: "/"))

        if basePath.isEmpty {
            components.path = "/\(endpoint)"
        } else if endpoint.isEmpty {
            components.path = "/\(basePath)"
        } else {
            components.path = "/\(basePath)/\(endpoint)"
        }

        return components.url ?? baseURL
    }

    private func validate(response: URLResponse, data: Data) throws {
        guard let http = response as? HTTPURLResponse else {
            throw APIError.transportError("Neplatná odpověď serveru")
        }

        let serverMessage = extractServerMessage(from: data)
        switch http.statusCode {
        case 200 ... 299:
            return
        case 401:
            let path = http.url?.path ?? ""
            if path.contains("/user/login") {
                if let serverMessage, !serverMessage.isEmpty {
                    throw APIError.serverError(serverMessage)
                }
                throw APIError.serverError("Neplatný email nebo heslo")
            }
            throw APIError.unauthorized
        case 403:
            throw APIError.serverError(serverMessage ?? "Nemáte oprávnění pro tuto akci.")
        default:
            let message = serverMessage ?? String(data: data, encoding: .utf8) ?? "Chyba API \(http.statusCode)"
            throw APIError.serverError(message)
        }
    }

    private func isLikelyCloudflareChallenge(data: Data) -> Bool {
        guard let text = String(data: data, encoding: .utf8)?.lowercased() else { return false }
        return text.contains("cloudflare") && text.contains("challenge")
    }

    private func extractServerMessage(from data: Data) -> String? {
        if
            let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        {
            if let detail = json["detail"] as? String, !detail.isEmpty {
                return detail
            }
            if
                let detail = json["detail"] as? [String: Any],
                let detailMessage = detail["message"] as? String,
                !detailMessage.isEmpty
            {
                return detailMessage
            }
            if
                let detailList = json["detail"] as? [[String: Any]],
                let first = detailList.first,
                let detailMessage = first["msg"] as? String,
                !detailMessage.isEmpty
            {
                return detailMessage
            }
            if let message = json["message"] as? String, !message.isEmpty {
                return message
            }
            if let error = json["error"] as? String, !error.isEmpty {
                return error
            }
            if
                let errorObj = json["error"] as? [String: Any],
                let message = errorObj["message"] as? String,
                !message.isEmpty
            {
                return message
            }
        }
        return nil
    }
}
