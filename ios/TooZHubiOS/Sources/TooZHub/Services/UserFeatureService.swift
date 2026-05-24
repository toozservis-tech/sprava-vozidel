import Foundation

final class UserFeatureService {
    private let api: APIClient

    init(api: APIClient) {
        self.api = api
    }

    func createVehicle(_ request: VehicleCreateRequest, token: String) async throws -> Vehicle {
        let body = try api.encodeBody(request)
        return try await api.request(.post("/api/v1/vehicles", body: body), token: token)
    }

    func updateVehicle(id: Int, _ request: VehicleCreateRequest, token: String) async throws -> Vehicle {
        let body = try api.encodeBody(request)
        return try await api.request(.put("/api/v1/vehicles/\(id)", body: body), token: token)
    }

    func updateVehiclePartial(id: Int, _ request: VehicleUpdateRequest, token: String) async throws -> Vehicle {
        let body = try api.encodeBody(request)
        return try await api.request(.put("/api/v1/vehicles/\(id)", body: body), token: token)
    }

    func removeVehicleFromAccount(id: Int, reasonCode: String, followupAnswer: [String: String], token: String) async throws -> VehicleRemovalConfirmResponse {
        let initBody = try api.encodeBody(VehicleRemovalInitBody(reasonCode: reasonCode))
        _ = try await api.request(
            VehicleRemovalInitResponse.self,
            .post("/api/v1/vehicles/\(id)/remove/init", body: initBody),
            token: token
        )
        let confirmBody = try api.encodeBody(
            VehicleRemovalConfirmBody(reasonCode: reasonCode, followupAnswer: followupAnswer)
        )
        return try await api.request(
            VehicleRemovalConfirmResponse.self,
            .post("/api/v1/vehicles/\(id)/remove/confirm", body: confirmBody),
            token: token
        )
    }

    func createServiceRecord(vehicleId: Int, _ request: ServiceRecordCreateRequest, token: String) async throws -> ServiceRecord {
        let body = try api.encodeBody(request)
        return try await api.request(.post("/api/v1/vehicles/\(vehicleId)/records", body: body), token: token)
    }

    func updateServiceRecord(vehicleId: Int, recordId: Int, _ request: ServiceRecordUpdateRequest, token: String) async throws -> ServiceRecord {
        let body = try api.encodeBody(request)
        return try await api.request(.put("/api/v1/vehicles/\(vehicleId)/records/\(recordId)", body: body), token: token)
    }

    func deleteServiceRecord(vehicleId: Int, recordId: Int, token: String) async throws {
        try await api.requestNoContent(.delete("/api/v1/vehicles/\(vehicleId)/records/\(recordId)"), token: token)
    }

    func uploadServiceRecordAttachment(
        vehicleId: Int,
        _ request: ServiceRecordAttachmentUploadRequest,
        token: String
    ) async throws -> ServiceRecordAttachmentUploadResponse {
        let body = try api.encodeBody(request)
        return try await api.request(.post("/api/v1/vehicles/\(vehicleId)/records/attachments/upload", body: body), token: token)
    }

    func previewServiceRecordFromDocument(
        vehicleId: Int,
        _ request: ServiceRecordDocumentPrefillRequest,
        token: String
    ) async throws -> ServiceRecordDocumentPrefillResponse {
        let body = try api.encodeBody(request)
        return try await api.request(.post("/api/v1/vehicles/\(vehicleId)/records/document-prefill", body: body), token: token)
    }

    func createReminder(_ request: ReminderCreateRequest, token: String) async throws -> Reminder {
        let body = try api.encodeBody(request)
        return try await api.request(.post("/api/v1/reminders", body: body), token: token)
    }

    func updateReminder(id: Int, _ request: ReminderUpdateRequest, token: String) async throws -> Reminder {
        let body = try api.encodeBody(request)
        return try await api.request(.put("/api/v1/reminders/\(id)", body: body), token: token)
    }

    func deleteReminder(id: Int, token: String) async throws {
        try await api.requestNoContent(.delete("/api/v1/reminders/\(id)"), token: token)
    }

    func fetchReminderSettings(token: String) async throws -> ReminderSettings {
        try await api.request(.get("/api/v1/reminders/settings"), token: token)
    }

    func updateReminderSettings(_ request: ReminderSettingsUpdateRequest, token: String) async throws -> ReminderSettings {
        let body = try api.encodeBody(request)
        return try await api.request(.put("/api/v1/reminders/settings", body: body), token: token)
    }

    func fetchServiceDiscovery(token: String) async throws -> ServicesDiscoveryResponse {
        do {
            return try await api.request(.get("/api/v1/services/discovery"), token: token)
        } catch let apiError as APIError {
            switch apiError {
            case .unauthorized, .forbidden:
                throw apiError
            default:
                break
            }
        } catch {
            // Fallback níže.
        }

        if let decoded = try? await decodeServiceContacts(endpoint: "/api/v1/services/discovery", token: token) {
            return ServicesDiscoveryResponse(
                meta: ServiceDiscoveryMeta(total: decoded.count),
                services: deduplicatedServiceContacts(decoded)
            )
        }
        if let decoded = try? await decodeServiceContacts(endpoint: "/api/v1/services", token: token) {
            return ServicesDiscoveryResponse(
                meta: ServiceDiscoveryMeta(total: decoded.count),
                services: deduplicatedServiceContacts(decoded)
            )
        }
        if let decoded = try? await decodeServiceContacts(endpoint: "/api/v1/services/my-contacts", token: token) {
            return ServicesDiscoveryResponse(
                meta: ServiceDiscoveryMeta(total: decoded.count),
                services: deduplicatedServiceContacts(decoded)
            )
        }
        return ServicesDiscoveryResponse(meta: ServiceDiscoveryMeta(), services: [])
    }

    func fetchMyServiceContacts(token: String) async throws -> ServiceContactsResponse {
        do {
            return try await api.request(.get("/api/v1/services/my-contacts"), token: token)
        } catch let apiError as APIError {
            switch apiError {
            case .unauthorized, .forbidden:
                throw apiError
            default:
                break
            }
        } catch {
            // Fallback níže.
        }

        if let decoded = try? await decodeServiceContacts(endpoint: "/api/v1/services/my-contacts", token: token) {
            return ServiceContactsResponse(services: deduplicatedServiceContacts(decoded))
        }
        return ServiceContactsResponse(services: [])
    }

    func fetchVehicleAccessGrants(token: String) async throws -> VehicleAccessGrantListResponse {
        try await api.request(.get("/api/v1/services/vehicle-access"), token: token)
    }

    func fetchServiceAccessRequests(token: String) async throws -> ServiceAccessRequestListResponse {
        try await api.request(.get("/api/v1/services/access-requests"), token: token)
    }

    func resolveServiceAccessRequest(
        requestId: Int,
        decision: String,
        note: String?,
        token: String
    ) async throws -> ServiceAccessRequestDecisionResponse {
        let body = try api.encodeBody(ServiceAccessRequestDecisionRequest(decision: decision, note: note))
        return try await api.request(.put("/api/v1/services/access-requests/\(requestId)", body: body), token: token)
    }

    func grantVehicleAccess(_ request: VehicleAccessGrantRequest, token: String) async throws {
        let body = try api.encodeBody(request)
        try await api.requestNoContent(.post("/api/v1/services/vehicle-access", body: body), token: token)
    }

    func revokeVehicleAccess(serviceId: Int, vehicleId: Int, token: String) async throws {
        try await api.requestNoContent(.delete("/api/v1/services/vehicle-access/\(serviceId)/\(vehicleId)"), token: token)
    }

    func disconnectService(serviceId: Int, token: String) async throws {
        try await api.requestNoContent(.delete("/api/v1/services/my-contacts/\(serviceId)"), token: token)
    }

    func updateReservationStatus(reservationId: Int, status: String, token: String) async throws -> Reservation {
        let payload = ["status": status]
        let body = try api.encodeBody(payload)
        return try await api.request(.put("/api/v1/reservations/\(reservationId)", body: body), token: token)
    }

    func deleteReservation(reservationId: Int, token: String) async throws {
        try await api.requestNoContent(.delete("/api/v1/reservations/\(reservationId)"), token: token)
    }

    func changePassword(_ request: ChangePasswordRequest, token: String) async throws {
        let body = try api.encodeBody(request)
        try await api.requestNoContent(.put("/user/change-password", body: body), token: token)
    }

    func sendSupport(_ request: SupportRequest, token: String) async throws {
        let body = try api.encodeBody(request)
        try await api.requestNoContent(.post("/user/support", body: body), token: token)
    }

    func downloadExport(token: String) async throws -> URL {
        let data = try await api.requestData(.get("/user/me/export"), token: token)
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("sprava_vozidel_export_\(Int(Date().timeIntervalSince1970)).zip")
        try data.write(to: url, options: .atomic)
        return url
    }

    func deleteAccount(_ request: DeleteAccountRequest, token: String) async throws {
        let body = try api.encodeBody(request)
        try await api.requestNoContent(.delete("/user/me", body: body), token: token)
    }

    private func decodeServiceContacts(endpoint: String, token: String) async throws -> [ServiceContact] {
        let data = try await api.requestData(.get(endpoint), token: token)
        let decoder = makeDecoder()

        if let response = try? decoder.decode(ServicesDiscoveryResponse.self, from: data), !response.services.isEmpty {
            return response.services
        }
        if let response = try? decoder.decode(ServiceContactsResponse.self, from: data), !response.services.isEmpty {
            return response.services
        }
        if let direct = try? decoder.decode([ServiceContact].self, from: data), !direct.isEmpty {
            return direct
        }
        if let nested = try? decoder.decode([[ServiceContact]].self, from: data), !nested.isEmpty {
            return nested.flatMap { $0 }
        }

        let dictionaries = collectServiceDictionaries(from: (try? JSONSerialization.jsonObject(with: data)) as Any)
        return dictionaries.compactMap { dictionary in
            guard let id = intValue(from: dictionary["id"]) else { return nil }
            let name = stringValue(from: dictionary["name"]) ?? stringValue(from: dictionary["email"]) ?? "Servis #\(id)"
            let email = stringValue(from: dictionary["email"]) ?? ""
            return ServiceContact(
                id: id,
                name: name,
                email: email,
                phone: stringValue(from: dictionary["phone"]),
                city: stringValue(from: dictionary["city"]),
                street: stringValue(from: dictionary["street"]) ?? stringValue(from: dictionary["address"]),
                streetNumber: stringValue(from: dictionary["street_number"]) ?? stringValue(from: dictionary["streetNumber"]),
                zip: stringValue(from: dictionary["zip"]),
                ico: stringValue(from: dictionary["ico"]),
                distanceKm: doubleValue(from: dictionary["distance_km"]) ?? doubleValue(from: dictionary["distanceKm"]),
                hasPreciseDistance: boolValue(from: dictionary["has_precise_distance"]) ?? boolValue(from: dictionary["hasPreciseDistance"]),
                isLinked: boolValue(from: dictionary["is_linked"]) ?? boolValue(from: dictionary["isLinked"]) ?? false,
                sharedVehiclesCount: intValue(from: dictionary["shared_vehicles_count"]) ?? intValue(from: dictionary["sharedVehiclesCount"]) ?? 0,
                createdAt: stringValue(from: dictionary["created_at"]) ?? stringValue(from: dictionary["createdAt"])
            )
        }
    }

    private func deduplicatedServiceContacts(_ contacts: [ServiceContact]) -> [ServiceContact] {
        var map: [Int: ServiceContact] = [:]
        for contact in contacts {
            map[contact.id] = contact
        }
        return map.values.sorted { lhs, rhs in
            lhs.name.localizedCaseInsensitiveCompare(rhs.name) == .orderedAscending
        }
    }

    private func collectServiceDictionaries(from value: Any?) -> [[String: Any]] {
        guard let value else { return [] }
        if let array = value as? [Any] {
            return array.flatMap { collectServiceDictionaries(from: $0) }
        }
        guard let dictionary = value as? [String: Any] else { return [] }

        var output: [[String: Any]] = []
        let lowercasedKeys = Set(dictionary.keys.map { $0.lowercased() })
        if lowercasedKeys.contains("id"), (lowercasedKeys.contains("name") || lowercasedKeys.contains("email")) {
            output.append(dictionary)
        }

        for key in ["services", "data", "items", "rows", "result", "results", "contacts"] {
            output.append(contentsOf: collectServiceDictionaries(from: dictionary[key]))
        }
        return output
    }

    private func makeDecoder() -> JSONDecoder {
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
        return decoder
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
            if let intValue = Int(normalized) {
                return intValue
            }
            if let doubleValue = Double(normalized) {
                return Int(doubleValue)
            }
            return nil
        default:
            return nil
        }
    }

    private func doubleValue(from value: Any?) -> Double? {
        switch value {
        case let value as Double:
            return value
        case let value as NSNumber:
            return value.doubleValue
        case let value as String:
            return Double(value.trimmingCharacters(in: .whitespacesAndNewlines).replacingOccurrences(of: ",", with: "."))
        default:
            return nil
        }
    }

    private func boolValue(from value: Any?) -> Bool? {
        switch value {
        case let value as Bool:
            return value
        case let value as NSNumber:
            return value.intValue != 0
        case let value as String:
            switch value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
            case "true", "1", "yes", "y":
                return true
            case "false", "0", "no", "n":
                return false
            default:
                return nil
            }
        default:
            return nil
        }
    }
}

private struct VehicleRemovalInitBody: Encodable {
    let reasonCode: String
}

private struct VehicleRemovalConfirmBody: Encodable {
    let reasonCode: String
    let followupAnswer: [String: String]
}

private struct VehicleRemovalInitResponse: Decodable {
    let vehicleId: Int?
}
