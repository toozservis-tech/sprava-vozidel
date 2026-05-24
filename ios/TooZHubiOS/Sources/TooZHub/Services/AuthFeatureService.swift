import Foundation

final class AuthFeatureService {
    private let api: APIClient

    init(api: APIClient) {
        self.api = api
    }

    func registerUser(_ request: UserRegisterRequest) async throws -> RegisterTokenResponse {
        let body = try api.encodeBody(request)
        return try await api.request(.post("/user/register", body: body), token: nil)
    }

    func registerServiceRequest(_ request: ServiceRegistrationRequest) async throws -> ServiceRegistrationResponse {
        let body = try api.encodeBody(request)
        return try await api.request(.post("/user/register/service-request", body: body), token: nil)
    }

    func requestPasswordReset(email: String) async throws -> ForgotPasswordResponse {
        let body = try api.encodeBody(ForgotPasswordRequest(email: email))
        return try await api.request(.post("/user/forgot-password", body: body), token: nil)
    }

    func lookupAresPublic(ico: String) async throws -> AresPublicResponse {
        let clean = ico.trimmingCharacters(in: .whitespacesAndNewlines)
        do {
            return try await api.request(.get("/user/ares", queryItems: [URLQueryItem(name: "ico", value: clean)]), token: nil)
        } catch APIError.decodingError {
            let data = try await api.requestData(.get("/user/ares", queryItems: [URLQueryItem(name: "ico", value: clean)]), token: nil)
            return try parseAresFallback(data: data)
        }
    }

    private func parseAresFallback(data: Data) throws -> AresPublicResponse {
        guard
            let object = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        else {
            throw APIError.decodingError
        }

        let sidlo = object["sidlo"] as? [String: Any]
        var sidloPayload: [String: Any] = [:]
        if let value = sidlo?["nazevUlice"] { sidloPayload["nazevUlice"] = value }
        if let value = sidlo?["cisloDomovni"] { sidloPayload["cisloDomovni"] = value }
        if let value = sidlo?["cisloOrientacni"] { sidloPayload["cisloOrientacni"] = value }
        if let value = sidlo?["cisloOrientacniPismeno"] { sidloPayload["cisloOrientacniPismeno"] = value }
        if let value = sidlo?["nazevObce"] { sidloPayload["nazevObce"] = value }
        if let value = sidlo?["psc"] { sidloPayload["psc"] = value }

        var payload: [String: Any] = [:]
        if let value = object["ico"] { payload["ico"] = value }
        if let value = object["company_name"] { payload["companyName"] = value }
        if let value = object["obchodniJmeno"] { payload["obchodniJmeno"] = value }
        if let value = object["nazev"] { payload["nazev"] = value }
        if let value = object["dic"] { payload["dic"] = value }
        if let value = object["street"] { payload["street"] = value }
        if let value = object["house_number"] { payload["houseNumber"] = value }
        if let value = object["city"] { payload["city"] = value }
        if let value = object["zip"] { payload["zip"] = value }
        if !sidloPayload.isEmpty { payload["sidlo"] = sidloPayload }

        let normalizedData = try JSONSerialization.data(withJSONObject: payload, options: [])
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(AresPublicResponse.self, from: normalizedData)
    }
}
