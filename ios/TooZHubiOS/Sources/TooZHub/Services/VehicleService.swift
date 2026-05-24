import Foundation

final class VehicleService {
    private let api: APIClient
    private static let directTachometerClient = DirectTachometerClient()
    private let orvParseTimeout: TimeInterval = 90

    init(api: APIClient) {
        self.api = api
    }

    func fetchVehicles(token: String) async throws -> [Vehicle] {
        try await api.request(.get("/api/v1/vehicles"), token: token)
    }

    func fetchVehicleDetail(id: Int, token: String) async throws -> Vehicle {
        try await api.request(.get("/api/v1/vehicles/\(id)"), token: token)
    }

    func fetchServiceRecords(vehicleId: Int, token: String) async throws -> [ServiceRecord] {
        try await api.request(.get("/api/v1/vehicles/\(vehicleId)/records"), token: token)
    }

    func fetchVehiclePhotoData(vehicleId: Int, token: String) async throws -> Data {
        try await api.requestData(.get("/api/v1/vehicles/\(vehicleId)/photo"), token: token)
    }

    func uploadVehiclePhoto(
        vehicleId: Int,
        request: VehiclePhotoUploadRequest,
        token: String
    ) async throws -> VehiclePhotoUploadResponse {
        let body = try api.encodeBody(request)
        return try await api.request(.post("/api/v1/vehicles/\(vehicleId)/photo", body: body), token: token)
    }

    func deleteVehiclePhoto(vehicleId: Int, token: String) async throws {
        try await api.requestNoContent(.delete("/api/v1/vehicles/\(vehicleId)/photo"), token: token)
    }

    func recordMileage(
        vehicleId: Int,
        request: VehicleMileageRecordRequest,
        token: String
    ) async throws -> VehicleMileageRecordResponse {
        let body = try api.encodeBody(request)
        return try await api.request(.post("/api/v1/vehicles/\(vehicleId)/mileage", body: body), token: token)
    }

    func lookupVIN(_ vin: String, token: String) async throws -> VinLookupResponse {
        let clean = vin.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        let escaped = clean.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? clean
        return try await api.request(.get("/api/v1/vin/\(escaped)"), token: token)
    }

    func initVehicleTachometer(vehicleId: Int, token: String) async throws -> VehicleTachometerInitResponse {
        try await api.request(.post("/api/v1/vehicles/\(vehicleId)/tachometer/init"), token: token)
    }

    func submitVehicleTachometer(
        vehicleId: Int,
        sessionId: String,
        captchaCode: String,
        token: String
    ) async throws -> VehicleTachometerSubmitResponse {
        let body = try api.encodeBody(
            VehicleTachometerSubmitRequest(
                sessionId: sessionId,
                captchaCode: captchaCode
            )
        )
        return try await api.request(
            .post("/api/v1/vehicles/\(vehicleId)/tachometer/submit", body: body),
            token: token
        )
    }

    func fetchVehicleTachometerHistory(vehicleId: Int, token: String) async throws -> [VehicleInspectionHistoryEntry] {
        let data = try await api.requestData(.get("/api/v1/vehicles/\(vehicleId)/tachometer/history"), token: token)
        return try parseVehicleInspectionHistory(from: data)
    }

    func decodeVINDetailed(_ vin: String, token: String) async throws -> DecoderResponse {
        let clean = vin.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        let body = try api.encodeBody(["vin": clean])
        return try await api.request(.post("/api/vehicles/decode-vin", body: body), token: token)
    }

    func decodePlate(_ plate: String, token: String) async throws -> DecoderResponse {
        let body = try api.encodeBody(["plate": plate])
        return try await api.request(.post("/api/vehicles/decode-plate", body: body), token: token)
    }

    func parseORV(_ request: ORVParseRequest, token: String) async throws -> ORVParseResponse {
        let body = try api.encodeBody(request)
        return try await api.request(
            .post("/api/v1/vehicles/parse-orv", body: body, timeoutInterval: orvParseTimeout),
            token: token
        )
    }

    func createTachometerChallenge(vin: String? = nil, token: String) async throws -> TachometerChallengeResponse {
        let normalizedVIN = vin?
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .uppercased()

        do {
            let body = try api.encodeBody(TachometerChallengeRequestBody(vin: normalizedVIN))
            return try await api.request(.post("/api/v1/vehicles/tachometer/challenge", body: body), token: token)
        } catch {
#if DEBUG
            print("[Tachometer] API challenge failed, switching to direct fallback: \(error.localizedDescription)")
#endif
            return try await Self.directTachometerClient.createChallenge(vin: normalizedVIN)
        }
    }

    func lookupTachometer(
        challengeId: String,
        vin: String,
        captchaCode: String,
        token: String
    ) async throws -> TachometerLookupResponse {
        if await Self.directTachometerClient.hasChallenge(challengeId) {
            return try await Self.directTachometerClient.lookup(
                challengeId: challengeId,
                vin: vin,
                captchaCode: captchaCode
            )
        }

        let body = try api.encodeBody(
            TachometerLookupRequestBody(
                challengeId: challengeId,
                vin: vin,
                captchaCode: captchaCode
            )
        )

        do {
            return try await api.request(.post("/api/v1/vehicles/tachometer/lookup", body: body), token: token)
        } catch {
#if DEBUG
            print("[Tachometer] API lookup failed, switching to direct fallback: \(error.localizedDescription)")
#endif
            return try await Self.directTachometerClient.lookup(
                challengeId: challengeId,
                vin: vin,
                captchaCode: captchaCode
            )
        }
    }

    func downloadVehicleReportPDF(vehicleId: Int, token: String) async throws -> URL {
        let data = try await api.requestData(.get("/api/v1/vehicles/\(vehicleId)/pdf"), token: token)
        return try saveTemporaryFile(
            data: data,
            filename: "vehicle_history_\(vehicleId)_\(Int(Date().timeIntervalSince1970)).pdf"
        )
    }

    private func shouldUseDirectTachometerFallback(for error: APIError) -> Bool {
        // Získej zprávu z APIError, preferuj specifické případy, jinak použij localizedDescription
        let primaryMessage: String
        switch error {
        case .serverError(let message):
            primaryMessage = message
        case .transportError(let message):
            primaryMessage = message
        default:
            primaryMessage = error.localizedDescription
        }

        func matchesNotSupported(_ text: String) -> Bool {
            let lowered = text.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            return lowered.contains("404")
                || lowered.contains("not found")
                || lowered.contains("501")
                || lowered.contains("not implemented")
        }

        if matchesNotSupported(primaryMessage) { return true }

        // Pro jistotu zkontroluj i celkový popis chyby
        return matchesNotSupported(error.localizedDescription)
    }

    private func shouldUseDirectTachometerFallback(for error: Error) -> Bool {
        let lowered = error.localizedDescription.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return lowered.contains("404")
            || lowered.contains("not found")
            || lowered.contains("501")
            || lowered.contains("not implemented")
    }

    private func saveTemporaryFile(data: Data, filename: String) throws -> URL {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(filename)
        try data.write(to: url, options: .atomic)
        return url
    }
}

private func parseVehicleInspectionHistory(from data: Data) throws -> [VehicleInspectionHistoryEntry] {
    let object = try JSONSerialization.jsonObject(with: data)
    let dictionaries = unwrapDictionaryArray(object, candidateKeys: [
        "items",
        "history",
        "inspections",
        "results",
        "rows",
        "data",
    ])

    return dictionaries.enumerated().compactMap { index, raw in
        let mileage = intValue(from: raw["mileage_km"] ?? raw["latest_stk_odometer_km"] ?? raw["odometer_km"])
        let checkDate = dateValue(from: raw["check_date"] ?? raw["latest_stk_odometer_date"] ?? raw["inspection_date"])
        let source = stringValue(from: raw["source"] ?? raw["latest_stk_source"])
        let status = stringValue(from: raw["status"] ?? raw["latest_stk_import_status"])
        let protocolNumber = stringValue(from: raw["protocol_number"] ?? raw["protocolNumber"])
        let inspectionType = stringValue(from: raw["inspection_type"] ?? raw["inspectionType"])
        let summary = stringValue(from: raw["summary"])
        let documents = parseVehicleInspectionDocuments(from: raw["documents"])
        let hasDocuments = boolValue(from: raw["has_documents"]) ?? documents.contains(where: \.available)
        let documentsCount = intValue(from: raw["documents_count"]) ?? documents.filter(\.available).count
        let fallbackId = intValue(from: raw["id"]) ?? index

        return VehicleInspectionHistoryEntry(
            id: fallbackId,
            checkDate: checkDate,
            mileageKm: mileage,
            source: source,
            status: status,
            protocolNumber: protocolNumber,
            inspectionType: inspectionType,
            summary: summary,
            hasDocuments: hasDocuments,
            documentsCount: documentsCount,
            documents: documents
        )
    }
}

private func parseVehicleInspectionDocuments(from value: Any?) -> [VehicleInspectionHistoryDocument] {
    guard let dictionaries = value as? [[String: Any]] else { return [] }
    return dictionaries.enumerated().map { index, raw in
        let fallbackId = stringValue(from: raw["document_id"]) ?? "document-\(index)"
        return VehicleInspectionHistoryDocument(
            id: fallbackId,
            title: stringValue(from: raw["title"]) ?? "Dokument",
            documentType: stringValue(from: raw["document_type"]) ?? "document",
            available: boolValue(from: raw["available"]) ?? false,
            openMode: stringValue(from: raw["open_mode"]) ?? "unavailable",
            reason: stringValue(from: raw["reason"]),
            externalURL: stringValue(from: raw["external_url"]),
            internalProxyURL: stringValue(from: raw["internal_proxy_url"])
        )
    }
}

private func unwrapDictionaryArray(_ object: Any, candidateKeys: [String]) -> [[String: Any]] {
    if let dictionaries = object as? [[String: Any]] {
        return dictionaries
    }
    guard let root = object as? [String: Any] else { return [] }

    for key in candidateKeys {
        if let dictionaries = root[key] as? [[String: Any]] {
            return dictionaries
        }
    }
    return []
}

private func stringValue(from value: Any?) -> String? {
    switch value {
    case let value as String:
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    case let value as NSNumber:
        return value.stringValue
    default:
        return nil
    }
}

private func intValue(from value: Any?) -> Int? {
    switch value {
    case let value as Int:
        return value
    case let value as NSNumber:
        return value.intValue
    case let value as String:
        let normalized = value.trimmingCharacters(in: .whitespacesAndNewlines).replacingOccurrences(of: ",", with: ".")
        if let integer = Int(normalized) {
            return integer
        }
        if let double = Double(normalized) {
            return Int(double)
        }
        return nil
    default:
        return nil
    }
}

private func boolValue(from value: Any?) -> Bool? {
    switch value {
    case let value as Bool:
        return value
    case let value as NSNumber:
        return value.boolValue
    case let value as String:
        let normalized = value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if ["true", "1", "yes"].contains(normalized) { return true }
        if ["false", "0", "no"].contains(normalized) { return false }
        return nil
    default:
        return nil
    }
}

private func dateValue(from value: Any?) -> Date? {
    if let value = value as? Date {
        return value
    }
    if let timestamp = value as? Double {
        return Date(timeIntervalSince1970: timestamp)
    }
    if let timestamp = value as? Int {
        return Date(timeIntervalSince1970: Double(timestamp))
    }
    guard let text = stringValue(from: value) else { return nil }

    let formatter = DateFormatter()
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.timeZone = TimeZone(secondsFromGMT: 0)
    for format in [
        "yyyy-MM-dd'T'HH:mm:ss.SSSSSS",
        "yyyy-MM-dd'T'HH:mm:ss.SSS",
        "yyyy-MM-dd'T'HH:mm:ss",
        "yyyy-MM-dd",
        "dd.MM.yyyy",
    ] {
        formatter.dateFormat = format
        if let parsed = formatter.date(from: text) {
            return parsed
        }
    }
    return ISO8601DateFormatter().date(from: text)
}

private actor DirectTachometerClient {
    private struct StoredChallenge {
        let requestVerificationToken: String
        let captchaFieldName: String
        let session: URLSession
        let cookies: [HTTPCookie]
        let expectedVIN: String?
        let createdAt: Date
    }

    private let baseURL = URL(string: "https://www.kontrolatachometru.cz")!
    private let landingURL = URL(string: "https://www.kontrolatachometru.cz/")!
    private let searchURL = URL(string: "https://www.kontrolatachometru.cz/Home/Search")!
    private let timeout: TimeInterval = 20
    private let ttl: TimeInterval = 10 * 60
    private var challengeStore: [String: StoredChallenge] = [:]

    func hasChallenge(_ challengeId: String) -> Bool {
        cleanupExpiredChallenges()
        return challengeStore[challengeId] != nil
    }

    func createChallenge(vin: String? = nil) async throws -> TachometerChallengeResponse {
        cleanupExpiredChallenges()
        let cookieStorage = HTTPCookieStorage()
        let session = makeSession(cookieStorage: cookieStorage)

        let pageData = try await loadPage(session: session, url: landingURL)
        guard let pageHTML = String(data: pageData, encoding: .utf8) else {
            throw APIError.serverError("Nepodařilo se zpracovat stránku Kontroly tachometru.")
        }

        guard
            let requestVerificationToken = extractFirstMatch(
                in: pageHTML,
                pattern: #"name="__RequestVerificationToken"\s+type="hidden"\s+value="([^"]+)""#
            ),
            let captchaSrc = extractFirstMatch(
                in: pageHTML,
                pattern: #"<img[^>]+id="captcha_IMG"[^>]+src="([^"]+)""#
            )
        else {
            throw APIError.serverError("Nepodařilo se načíst captcha challenge z Kontroly tachometru.")
        }

        let captchaFieldName = extractFirstMatch(
            in: pageHTML,
            pattern: #"<input[^>]+name=\"([^\"]*captcha[^\"]*)\"[^>]*>"#,
            options: [.caseInsensitive]
        ) ?? "captcha$TB"

        let captchaData: Data
        let captchaMimeType: String
        do {
            let captchaURL = URL(string: decodeHTMLEntities(captchaSrc), relativeTo: baseURL) ?? baseURL
            var request = URLRequest(url: captchaURL)
            request.httpMethod = "GET"
            request.timeoutInterval = timeout
            applyCommonHeaders(to: &request)
            let (data, response) = try await session.data(for: request)
            guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
                throw APIError.serverError("Captcha obrázek se nepodařilo načíst.")
            }
            captchaData = data
            captchaMimeType = (http.value(forHTTPHeaderField: "Content-Type") ?? "image/png")
                .split(separator: ";")
                .first
                .map(String.init) ?? "image/png"
        } catch let error as APIError {
            throw error
        } catch {
            throw APIError.transportError("Nepodařilo se stáhnout captcha obrázek: \(error.localizedDescription)")
        }

        let challengeId = UUID().uuidString
        challengeStore[challengeId] = StoredChallenge(
            requestVerificationToken: decodeHTMLEntities(requestVerificationToken),
            captchaFieldName: captchaFieldName,
            session: session,
            cookies: cookieStorage.cookies ?? [],
            expectedVIN: normalizeVIN(vin ?? ""),
            createdAt: Date()
        )

        return TachometerChallengeResponse(
            challengeId: challengeId,
            captchaImageBase64: captchaData.base64EncodedString(),
            captchaMimeType: captchaMimeType,
            expiresInSeconds: Int(ttl)
        )
    }

    func lookup(
        challengeId: String,
        vin: String,
        captchaCode: String
    ) async throws -> TachometerLookupResponse {
        cleanupExpiredChallenges()
        guard let challenge = challengeStore[challengeId] else {
            throw APIError.serverError("Captcha challenge vypršel. Načtěte nový obrázek.")
        }

        let normalizedVIN = normalizeVIN(vin)
        guard normalizedVIN.count == 17 else {
            throw APIError.serverError("VIN musí mít přesně 17 znaků.")
        }
        if let expectedVIN = challenge.expectedVIN, !expectedVIN.isEmpty, expectedVIN != normalizedVIN {
            throw APIError.serverError("Captcha challenge patří k jinému vozidlu. Načtěte nový obrázek pro aktuální VIN.")
        }

        let trimmedCaptcha = captchaCode.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmedCaptcha.count >= 2 else {
            throw APIError.serverError("Zadejte captcha kód z obrázku.")
        }

        var request = URLRequest(url: searchURL)
        request.httpMethod = "POST"
        request.timeoutInterval = timeout
        applyCommonHeaders(to: &request)
        request.setValue(landingURL.absoluteString, forHTTPHeaderField: "Referer")
        request.setValue(baseURL.absoluteString, forHTTPHeaderField: "Origin")
        request.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
        request.setValue("text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", forHTTPHeaderField: "Accept")
        request.setValue("cs-CZ,cs;q=0.9,en;q=0.8", forHTTPHeaderField: "Accept-Language")
        request.setValue("no-cache", forHTTPHeaderField: "Cache-Control")
        request.setValue("no-cache", forHTTPHeaderField: "Pragma")
        request.setValue("1", forHTTPHeaderField: "Upgrade-Insecure-Requests")
        request.httpBody = buildFormBody(
            values: [
                "__RequestVerificationToken": challenge.requestVerificationToken,
                "VIN": normalizedVIN,
                challenge.captchaFieldName: trimmedCaptcha,
            ]
        )

        let htmlText: String
        do {
            let (data, response) = try await challenge.session.data(for: request)

            guard let http = response as? HTTPURLResponse else {
                throw APIError.serverError("Nepodařilo se ověřit tachometr: neplatná odpověď serveru.")
            }

            if !(200...299).contains(http.statusCode) {
                let text = (String(data: data, encoding: .utf8) ?? "")
                    .trimmingCharacters(in: .whitespacesAndNewlines)
                let lowered = text.lowercased()
                let isHTML = lowered.contains("<!doctype") || lowered.contains("<html")

                // Typický případ: nesoulad/expirace antiforgery tokenu nebo chybějící cookie
                if http.statusCode == 400 || http.statusCode == 403 || (http.statusCode == 500 && isHTML) {
                    throw APIError.serverError("Captcha challenge vypršel. Načtěte nový obrázek.")
                }

                if !text.isEmpty {
                    let short = String(text.prefix(240))
                    throw APIError.serverError("Nepodařilo se ověřit tachometr: HTTP \(http.statusCode) – \(short)")
                }
                throw APIError.serverError("Nepodařilo se ověřit tachometr: HTTP \(http.statusCode).")
            }

            htmlText = String(data: data, encoding: .utf8) ?? ""
        } catch let error as APIError {
            throw error
        } catch {
            throw APIError.transportError("Nepodařilo se ověřit tachometr: \(error.localizedDescription)")
        }

        if containsCaptchaError(htmlText) {
            throw APIError.serverError("Špatně opsaný kód z obrázku")
        }

        let inspections = parseInspections(from: htmlText)
        guard let latest = inspections.first else {
            throw APIError.serverError("Pro zadané VIN nebyly nalezeny žádné údaje STK/emisí.")
        }

        challengeStore.removeValue(forKey: challengeId)

        return TachometerLookupResponse(
            vin: normalizedVIN,
            latestMileageKm: latest.mileageKm,
            latestCheckDate: latest.checkDate,
            inspections: inspections,
            source: "kontrolatachometru.cz"
        )
    }

    private func loadPage(session: URLSession, url: URL) async throws -> Data {
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.timeoutInterval = timeout
        applyCommonHeaders(to: &request)

        do {
            let (data, response) = try await session.data(for: request)
            guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
                throw APIError.serverError("Nepodařilo se načíst stránku Kontroly tachometru.")
            }
            return data
        } catch let error as APIError {
            throw error
        } catch {
            throw APIError.transportError("Nepodařilo se spojit s kontrolatachometru.cz: \(error.localizedDescription)")
        }
    }

    private func makeSession(cookieStorage: HTTPCookieStorage) -> URLSession {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.httpCookieStorage = cookieStorage
        configuration.httpShouldSetCookies = true
        configuration.timeoutIntervalForRequest = timeout
        configuration.timeoutIntervalForResource = timeout
        configuration.requestCachePolicy = .reloadIgnoringLocalAndRemoteCacheData
        return URLSession(configuration: configuration)
    }

    private func applyCommonHeaders(to request: inout URLRequest) {
        request.setValue(
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile",
            forHTTPHeaderField: "User-Agent"
        )
        request.setValue(
            "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            forHTTPHeaderField: "Accept"
        )
    }

    private func buildFormBody(values: [String: String]) -> Data? {
        let formString = values.map { key, value in
            "\(percentEncode(key))=\(percentEncode(value))"
        }
        .joined(separator: "&")
        return formString.data(using: .utf8)
    }

    private func percentEncode(_ raw: String) -> String {
        let allowed = CharacterSet(charactersIn: "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._* ")
        return raw
            .addingPercentEncoding(withAllowedCharacters: allowed)?
            .replacingOccurrences(of: " ", with: "+") ?? raw
    }

    private func cookieHeader(from cookies: [HTTPCookie]) -> String {
        cookies
            .map { "\($0.name)=\($0.value)" }
            .joined(separator: "; ")
    }

    private func normalizeVIN(_ raw: String) -> String {
        raw
            .uppercased()
            .unicodeScalars
            .filter { CharacterSet.alphanumerics.contains($0) }
            .map(String.init)
            .joined()
    }

    private func containsCaptchaError(_ html: String) -> Bool {
        let lowered = decodeHTMLEntities(html).lowercased()
        let ascii = lowered.folding(options: .diacriticInsensitive, locale: Locale(identifier: "cs_CZ"))
        return lowered.contains("špatně opsaný kód z obrázku")
            || ascii.contains("spatne opsany kod z obrazku")
            || lowered.contains("submitted code is incorrect")
    }

    private func parseInspections(from html: String) -> [TachometerInspection] {
        let rows = matches(in: html, pattern: #"<tr[^>]*data-row-id="[^"]+"[^>]*>.*?</tr>"#, options: [.dotMatchesLineSeparators, .caseInsensitive])
        let inspections = rows.compactMap { row -> TachometerInspection? in
            guard let mileageKm = parseMileage(extractTDValue(in: row, dataAttribute: "data-km-staff")) else {
                return nil
            }
            return TachometerInspection(
                checkDate: parseCZDate(extractTDValue(in: row, dataAttribute: "data-finish-date")),
                mileageKm: mileageKm,
                protocolNumber: cleanedText(extractTDValue(in: row, dataAttribute: "data-protocol-number")),
                inspectionType: cleanedText(extractTDValue(in: row, dataAttribute: "data-inspection-type-name"))
            )
        }

        return inspections.sorted { lhs, rhs in
            switch (lhs.checkDate, rhs.checkDate) {
            case let (l?, r?):
                if l == r { return lhs.mileageKm > rhs.mileageKm }
                return l > r
            case (_?, nil):
                return true
            case (nil, _?):
                return false
            case (nil, nil):
                return lhs.mileageKm > rhs.mileageKm
            }
        }
    }

    private func parseMileage(_ raw: String?) -> Int? {
        guard let raw else { return nil }
        let digits = cleanedText(raw)?.replacingOccurrences(of: "[^0-9]", with: "", options: .regularExpression) ?? ""
        return Int(digits)
    }

    private func parseCZDate(_ raw: String?) -> Date? {
        guard let raw = cleanedText(raw), !raw.isEmpty else { return nil }
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "cs_CZ")
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        for format in ["dd.MM.yyyy", "dd.MM.yyyy HH:mm", "dd.MM.yyyy HH:mm:ss", "yyyy-MM-dd"] {
            formatter.dateFormat = format
            if let parsed = formatter.date(from: raw) {
                return parsed
            }
        }
        return ISO8601DateFormatter().date(from: raw)
    }

    private func extractTDValue(in rowHTML: String, dataAttribute: String) -> String? {
        extractFirstMatch(
            in: rowHTML,
            pattern: #"<td[^>]*\#(NSRegularExpression.escapedPattern(for: dataAttribute))[^>]*>(.*?)</td>"#,
            options: [.dotMatchesLineSeparators, .caseInsensitive]
        )
    }

    private func cleanedText(_ raw: String?) -> String? {
        guard let raw, !raw.isEmpty else { return nil }
        let noTags = raw.replacingOccurrences(of: "<[^>]+>", with: " ", options: .regularExpression)
        let decoded = decodeHTMLEntities(noTags)
            .replacingOccurrences(of: "\u{00a0}", with: " ")
            .replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        return decoded.isEmpty ? nil : decoded
    }

    private func decodeHTMLEntities(_ raw: String) -> String {
        guard let data = raw.data(using: .utf8) else { return raw }
        let options: [NSAttributedString.DocumentReadingOptionKey: Any] = [
            .documentType: NSAttributedString.DocumentType.html,
            .characterEncoding: String.Encoding.utf8.rawValue,
        ]
        return (try? NSAttributedString(data: data, options: options, documentAttributes: nil).string) ?? raw
    }

    private func extractFirstMatch(
        in text: String,
        pattern: String,
        options: NSRegularExpression.Options = []
    ) -> String? {
        guard let regex = try? NSRegularExpression(pattern: pattern, options: options) else { return nil }
        let range = NSRange(text.startIndex..<text.endIndex, in: text)
        guard
            let match = regex.firstMatch(in: text, options: [], range: range),
            match.numberOfRanges > 1,
            let captureRange = Range(match.range(at: 1), in: text)
        else {
            return nil
        }
        return String(text[captureRange])
    }

    private func matches(
        in text: String,
        pattern: String,
        options: NSRegularExpression.Options = []
    ) -> [String] {
        guard let regex = try? NSRegularExpression(pattern: pattern, options: options) else { return [] }
        let range = NSRange(text.startIndex..<text.endIndex, in: text)
        return regex.matches(in: text, options: [], range: range).compactMap { match in
            guard let rowRange = Range(match.range(at: 0), in: text) else { return nil }
            return String(text[rowRange])
        }
    }

    private func cleanupExpiredChallenges() {
        let threshold = Date().addingTimeInterval(-ttl)
        challengeStore = challengeStore.filter { _, value in
            value.createdAt >= threshold
        }
    }
}
