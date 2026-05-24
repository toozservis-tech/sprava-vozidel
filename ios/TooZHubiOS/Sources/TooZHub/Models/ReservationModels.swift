import Foundation

struct Reservation: Codable, Identifiable, Hashable {
    let id: Int
    let serviceId: Int
    let customerId: Int
    let vehicleId: Int
    let serviceType: String?
    let note: String?
    let startDatetime: Date
    let endDatetime: Date?
    let status: String
    let createdAt: Date
    let serviceName: String?
    let serviceEmail: String?
    let customerName: String?
    let customerEmail: String?
    let vehicleName: String?
    let vehiclePlate: String?
    let sourcePlatform: String?
}

struct ReservationCreateRequest: Encodable {
    let serviceId: Int
    let vehicleId: Int
    let serviceType: String?
    let note: String?
    let startDatetime: Date
    let endDatetime: Date?
    let createdVia: String?
}

struct ReservationVehicleOption: Codable, Identifiable, Hashable {
    let id: Int
    let name: String
    let plate: String?
    let ownerEmail: String?
    let isShared: Bool
    let source: String?
}

struct ServicesDiscoveryResponse: Decodable {
    let meta: ServiceDiscoveryMeta
    let services: [ServiceContact]

    enum CodingKeys: String, CodingKey {
        case meta
        case services
    }

    init(meta: ServiceDiscoveryMeta, services: [ServiceContact]) {
        self.meta = meta
        self.services = services
    }

    init(from decoder: Decoder) throws {
        if let container = try? decoder.container(keyedBy: CodingKeys.self) {
            meta = (try? container.decode(ServiceDiscoveryMeta.self, forKey: .meta)) ?? ServiceDiscoveryMeta()

            if let direct = try? container.decode([ServiceContact].self, forKey: .services) {
                services = direct
                return
            }
            if let nested = try? container.decode([[ServiceContact]].self, forKey: .services) {
                services = nested.flatMap { $0 }
                return
            }
            services = []
            return
        }

        if let direct = try? [ServiceContact](from: decoder) {
            meta = ServiceDiscoveryMeta(total: direct.count)
            services = direct
            return
        }
        if let nested = try? [[ServiceContact]](from: decoder) {
            let flattened = nested.flatMap { $0 }
            meta = ServiceDiscoveryMeta(total: flattened.count)
            services = flattened
            return
        }

        meta = ServiceDiscoveryMeta()
        services = []
    }
}

struct ServiceDiscoveryMeta: Decodable {
    let total: Int
    let linkedTotal: Int
    let referenceSource: String
    let distanceSorted: Bool

    init(
        total: Int = 0,
        linkedTotal: Int = 0,
        referenceSource: String = "none",
        distanceSorted: Bool = false
    ) {
        self.total = total
        self.linkedTotal = linkedTotal
        self.referenceSource = referenceSource
        self.distanceSorted = distanceSorted
    }

    enum CodingKeys: String, CodingKey {
        case total
        case linkedTotal
        case referenceSource
        case distanceSorted
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        total = container.decodeFlexibleInt(forKey: .total) ?? 0
        linkedTotal = container.decodeFlexibleInt(forKey: .linkedTotal) ?? 0
        referenceSource = container.decodeFlexibleString(forKey: .referenceSource) ?? "none"
        distanceSorted = container.decodeFlexibleBool(forKey: .distanceSorted) ?? false
    }
}

struct ServiceContact: Decodable, Identifiable, Hashable {
    let id: Int
    let name: String
    let email: String
    let phone: String?
    let city: String?
    let street: String?
    let streetNumber: String?
    let zip: String?
    let ico: String?
    let distanceKm: Double?
    let hasPreciseDistance: Bool?
    let isLinked: Bool
    let sharedVehiclesCount: Int
    let createdAt: String?

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case email
        case phone
        case city
        case street
        case streetNumber
        case zip
        case ico
        case distanceKm
        case hasPreciseDistance
        case isLinked
        case sharedVehiclesCount
        case createdAt
        case address
    }

    init(
        id: Int,
        name: String,
        email: String,
        phone: String?,
        city: String?,
        street: String?,
        streetNumber: String?,
        zip: String?,
        ico: String?,
        distanceKm: Double?,
        hasPreciseDistance: Bool?,
        isLinked: Bool,
        sharedVehiclesCount: Int,
        createdAt: String?
    ) {
        self.id = id
        self.name = name
        self.email = email
        self.phone = phone
        self.city = city
        self.street = street
        self.streetNumber = streetNumber
        self.zip = zip
        self.ico = ico
        self.distanceKm = distanceKm
        self.hasPreciseDistance = hasPreciseDistance
        self.isLinked = isLinked
        self.sharedVehiclesCount = sharedVehiclesCount
        self.createdAt = createdAt
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)

        id = container.decodeFlexibleInt(forKey: .id) ?? 0
        let decodedName = container.decodeFlexibleString(forKey: .name)
        let decodedEmail = container.decodeFlexibleString(forKey: .email)
        name = decodedName ?? decodedEmail ?? "Servis #\(id)"
        email = decodedEmail ?? ""
        phone = container.decodeFlexibleString(forKey: .phone)
        city = container.decodeFlexibleString(forKey: .city)
        street = container.decodeFlexibleString(forKey: .street) ?? container.decodeFlexibleString(forKey: .address)
        streetNumber = container.decodeFlexibleString(forKey: .streetNumber)
        zip = container.decodeFlexibleString(forKey: .zip)
        ico = container.decodeFlexibleString(forKey: .ico)
        distanceKm = container.decodeFlexibleDouble(forKey: .distanceKm)
        hasPreciseDistance = container.decodeFlexibleBool(forKey: .hasPreciseDistance)
        isLinked = container.decodeFlexibleBool(forKey: .isLinked) ?? false
        sharedVehiclesCount = container.decodeFlexibleInt(forKey: .sharedVehiclesCount) ?? 0
        createdAt = container.decodeFlexibleString(forKey: .createdAt)
    }
}

private extension KeyedDecodingContainer {
    func decodeFlexibleString(forKey key: K) -> String? {
        if let value = try? decodeIfPresent(String.self, forKey: key) {
            let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
            if trimmed.isEmpty { return nil }
            if trimmed.lowercased() == "null" || trimmed.lowercased() == "nil" { return nil }
            return trimmed
        }
        if let intValue = try? decodeIfPresent(Int.self, forKey: key) {
            return String(intValue)
        }
        if let doubleValue = try? decodeIfPresent(Double.self, forKey: key) {
            return String(doubleValue)
        }
        if let boolValue = try? decodeIfPresent(Bool.self, forKey: key) {
            return boolValue ? "true" : "false"
        }
        return nil
    }

    func decodeFlexibleInt(forKey key: K) -> Int? {
        if let value = try? decodeIfPresent(Int.self, forKey: key) {
            return value
        }
        if let value = try? decodeIfPresent(Double.self, forKey: key) {
            return Int(value)
        }
        if let value = decodeFlexibleString(forKey: key) {
            let normalized = value.replacingOccurrences(of: ",", with: ".")
            if let intValue = Int(normalized) {
                return intValue
            }
            if let doubleValue = Double(normalized) {
                return Int(doubleValue)
            }
        }
        return nil
    }

    func decodeFlexibleDouble(forKey key: K) -> Double? {
        if let value = try? decodeIfPresent(Double.self, forKey: key) {
            return value
        }
        if let value = try? decodeIfPresent(Int.self, forKey: key) {
            return Double(value)
        }
        if let value = decodeFlexibleString(forKey: key) {
            return Double(value.replacingOccurrences(of: ",", with: "."))
        }
        return nil
    }

    func decodeFlexibleBool(forKey key: K) -> Bool? {
        if let value = try? decodeIfPresent(Bool.self, forKey: key) {
            return value
        }
        if let value = try? decodeIfPresent(Int.self, forKey: key) {
            return value != 0
        }
        if let value = decodeFlexibleString(forKey: key)?.lowercased() {
            switch value {
            case "true", "1", "yes", "y":
                return true
            case "false", "0", "no", "n":
                return false
            default:
                return nil
            }
        }
        return nil
    }
}
