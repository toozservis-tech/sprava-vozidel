import Foundation

final class ReservationService {
    private let api: APIClient

    init(api: APIClient) {
        self.api = api
    }

    func fetchReservations(token: String) async throws -> [Reservation] {
        try await fetchReservationsFlexible(path: "/api/v1/reservations/my", token: token)
    }

    func fetchServiceReservations(token: String) async throws -> [Reservation] {
        try await fetchReservationsFlexible(path: "/api/v1/reservations/service", token: token)
    }

    func fetchServiceDiscovery(token: String) async throws -> [ServiceContact] {
        do {
            let response: ServicesDiscoveryResponse = try await api.request(.get("/api/v1/services/discovery"), token: token)
            return response.services
        } catch {
            if let decoded = try? await decodeServiceContacts(endpoint: "/api/v1/services/discovery", token: token) {
                return deduplicatedServiceContacts(decoded)
            }
            if let decoded = try? await decodeServiceContacts(endpoint: "/api/v1/services", token: token) {
                return deduplicatedServiceContacts(decoded)
            }
            if let decoded = try? await decodeServiceContacts(endpoint: "/api/v1/services/my-contacts", token: token) {
                return deduplicatedServiceContacts(decoded)
            }
            throw error
        }
    }

    func fetchMyServiceContacts(token: String) async throws -> [ServiceContact] {
        do {
            let response: ServiceContactsResponse = try await api.request(.get("/api/v1/services/my-contacts"), token: token)
            return response.services
        } catch {
            if let decoded = try? await decodeServiceContacts(endpoint: "/api/v1/services/my-contacts", token: token) {
                return deduplicatedServiceContacts(decoded)
            }
            throw error
        }
    }

    func fetchReservationVehicleOptions(token: String) async throws -> [ReservationVehicleOption] {
        do {
            let options: [ReservationVehicleOption] = try await api.request(.get("/api/v1/reservations/vehicle-options"), token: token)
            if !options.isEmpty {
                return options
            }
        } catch {
            if let decoded = try? await decodeVehicleOptions(endpoint: "/api/v1/reservations/vehicle-options", token: token), !decoded.isEmpty {
                return deduplicatedVehicleOptions(decoded)
            }
        }

        // Fallback kompatibility pro starší backend: načteme klasický seznam vozidel.
        if let vehicles = try? await decodeVehicleOptions(endpoint: "/api/v1/vehicles", token: token), !vehicles.isEmpty {
            return deduplicatedVehicleOptions(vehicles)
        }

        let vehicles: [Vehicle] = try await api.request(.get("/api/v1/vehicles"), token: token)
        let mapped = vehicles.map { vehicle in
            ReservationVehicleOption(
                id: vehicle.id,
                name: vehicle.displayName,
                plate: vehicle.plate,
                ownerEmail: vehicle.userEmail,
                isShared: false,
                source: "legacy_vehicles_api"
            )
        }
        return deduplicatedVehicleOptions(mapped)
    }

    func createReservation(_ request: ReservationCreateRequest, token: String) async throws -> Reservation {
        let body = try api.encodeBody(request)
        return try await api.request(.post("/api/v1/reservations", body: body), token: token)
    }

    private func fetchReservationsFlexible(path: String, token: String) async throws -> [Reservation] {
        do {
            let direct: [Reservation] = try await api.request(.get(path), token: token)
            return direct
        } catch let apiError as APIError {
            switch apiError {
            case .unauthorized, .forbidden:
                throw apiError
            default:
                break
            }
        } catch {
            // Fallback níže
        }

        let data = try await api.requestData(.get(path), token: token)
        return parseReservations(from: data)
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
        let contacts = dictionaries.compactMap { dictionary -> ServiceContact? in
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
        return contacts
    }

    private func decodeVehicleOptions(endpoint: String, token: String) async throws -> [ReservationVehicleOption] {
        let data = try await api.requestData(.get(endpoint), token: token)
        let decoder = makeDecoder()

        if let direct = try? decoder.decode([ReservationVehicleOption].self, from: data), !direct.isEmpty {
            return direct
        }
        if let nested = try? decoder.decode([[ReservationVehicleOption]].self, from: data), !nested.isEmpty {
            return nested.flatMap { $0 }
        }

        let rawObject = try? JSONSerialization.jsonObject(with: data)
        let dictionaries = collectVehicleDictionaries(from: rawObject as Any)

        return dictionaries.compactMap { dictionary in
            guard let id = intValue(from: dictionary["id"]) else { return nil }

            let explicitName = stringValue(from: dictionary["name"])
            let brand = stringValue(from: dictionary["brand"])
            let model = stringValue(from: dictionary["model"])
            let nickname = stringValue(from: dictionary["nickname"])
            let composedName = [brand, model].compactMap { $0 }.joined(separator: " ").trimmingCharacters(in: .whitespacesAndNewlines)
            let fallbackName = [nickname, composedName, stringValue(from: dictionary["plate"])].compactMap { $0 }.first
            let name = explicitName ?? fallbackName ?? "Vozidlo #\(id)"

            return ReservationVehicleOption(
                id: id,
                name: name,
                plate: stringValue(from: dictionary["plate"]),
                ownerEmail: stringValue(from: dictionary["owner_email"]) ?? stringValue(from: dictionary["ownerEmail"]) ?? stringValue(from: dictionary["user_email"]) ?? stringValue(from: dictionary["userEmail"]),
                isShared: boolValue(from: dictionary["is_shared"]) ?? boolValue(from: dictionary["isShared"]) ?? false,
                source: stringValue(from: dictionary["source"]) ?? "fallback_parser"
            )
        }
    }

    private func parseReservations(from data: Data) -> [Reservation] {
        let decoder = makeDecoder()
        if let direct = try? decoder.decode([Reservation].self, from: data) {
            return direct
        }
        if let nested = try? decoder.decode([[Reservation]].self, from: data) {
            return nested.flatMap { $0 }
        }

        let dictionaries = collectReservationDictionaries(from: (try? JSONSerialization.jsonObject(with: data)) as Any)
        var output: [Reservation] = []
        for dictionary in dictionaries {
            guard
                let id = intValue(from: dictionary["id"]),
                let serviceId = intValue(from: dictionary["service_id"]) ?? intValue(from: dictionary["serviceId"]),
                let customerId = intValue(from: dictionary["customer_id"]) ?? intValue(from: dictionary["customerId"]),
                let vehicleId = intValue(from: dictionary["vehicle_id"]) ?? intValue(from: dictionary["vehicleId"]),
                let startDatetime = dateValue(from: dictionary["start_datetime"]) ?? dateValue(from: dictionary["startDatetime"])
            else {
                continue
            }

            let createdAt = dateValue(from: dictionary["created_at"]) ?? dateValue(from: dictionary["createdAt"]) ?? startDatetime
            let item = Reservation(
                id: id,
                serviceId: serviceId,
                customerId: customerId,
                vehicleId: vehicleId,
                serviceType: stringValue(from: dictionary["service_type"]) ?? stringValue(from: dictionary["serviceType"]),
                note: stringValue(from: dictionary["note"]),
                startDatetime: startDatetime,
                endDatetime: dateValue(from: dictionary["end_datetime"]) ?? dateValue(from: dictionary["endDatetime"]),
                status: stringValue(from: dictionary["status"]) ?? "PENDING",
                createdAt: createdAt,
                serviceName: stringValue(from: dictionary["service_name"]) ?? stringValue(from: dictionary["serviceName"]),
                serviceEmail: stringValue(from: dictionary["service_email"]) ?? stringValue(from: dictionary["serviceEmail"]),
                customerName: stringValue(from: dictionary["customer_name"]) ?? stringValue(from: dictionary["customerName"]),
                customerEmail: stringValue(from: dictionary["customer_email"]) ?? stringValue(from: dictionary["customerEmail"]),
                vehicleName: stringValue(from: dictionary["vehicle_name"]) ?? stringValue(from: dictionary["vehicleName"]),
                vehiclePlate: stringValue(from: dictionary["vehicle_plate"]) ?? stringValue(from: dictionary["vehiclePlate"]),
                sourcePlatform: stringValue(from: dictionary["source_platform"]) ?? stringValue(from: dictionary["sourcePlatform"])
            )
            output.append(item)
        }
        return output
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

    private func deduplicatedVehicleOptions(_ options: [ReservationVehicleOption]) -> [ReservationVehicleOption] {
        var map: [Int: ReservationVehicleOption] = [:]
        for option in options {
            map[option.id] = option
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

    private func collectVehicleDictionaries(from value: Any?) -> [[String: Any]] {
        guard let value else { return [] }
        if let array = value as? [Any] {
            return array.flatMap { collectVehicleDictionaries(from: $0) }
        }
        guard let dictionary = value as? [String: Any] else { return [] }

        var output: [[String: Any]] = []
        let lowercasedKeys = Set(dictionary.keys.map { $0.lowercased() })
        if lowercasedKeys.contains("id"), (lowercasedKeys.contains("name") || lowercasedKeys.contains("plate") || lowercasedKeys.contains("vin")) {
            output.append(dictionary)
        }

        for key in ["vehicles", "vehicle_options", "vehicleOptions", "data", "items", "rows", "result", "results"] {
            output.append(contentsOf: collectVehicleDictionaries(from: dictionary[key]))
        }
        return output
    }

    private func collectReservationDictionaries(from value: Any?) -> [[String: Any]] {
        guard let value else { return [] }
        if let array = value as? [Any] {
            return array.flatMap { collectReservationDictionaries(from: $0) }
        }
        guard let dictionary = value as? [String: Any] else { return [] }

        var output: [[String: Any]] = []
        let lowercasedKeys = Set(dictionary.keys.map { $0.lowercased() })
        if lowercasedKeys.contains("id"), (lowercasedKeys.contains("service_id") || lowercasedKeys.contains("serviceid")),
           lowercasedKeys.contains("vehicle_id") || lowercasedKeys.contains("vehicleid") {
            output.append(dictionary)
        }

        for key in ["reservations", "data", "items", "rows", "result", "results"] {
            output.append(contentsOf: collectReservationDictionaries(from: dictionary[key]))
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

    private func dateValue(from value: Any?) -> Date? {
        guard let raw = stringValue(from: value) else { return nil }
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        for format in ["yyyy-MM-dd'T'HH:mm:ss.SSSSSS", "yyyy-MM-dd'T'HH:mm:ss.SSS", "yyyy-MM-dd'T'HH:mm:ss", "yyyy-MM-dd"] {
            formatter.dateFormat = format
            if let parsed = formatter.date(from: raw) {
                return parsed
            }
        }
        return ISO8601DateFormatter().date(from: raw)
    }
}
