import Foundation

struct ServiceRecord: Codable, Identifiable, Hashable {
    let id: Int
    let vehicleId: Int
    let userId: Int?
    let performedAt: Date?
    let mileage: Int?
    let description: String
    let price: Double?
    let note: String?
    let category: String?
    let attachments: String?
    let nextServiceDueDate: Date?
    let createdByAI: Bool

    enum CodingKeys: String, CodingKey {
        case id
        case vehicleId
        case userId
        case performedAt
        case mileage
        case description
        case price
        case note
        case category
        case attachments
        case nextServiceDueDate
        case createdByAI
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)

        id = container.decodeFlexibleInt(forKey: .id) ?? 0
        vehicleId = container.decodeFlexibleInt(forKey: .vehicleId) ?? 0
        userId = container.decodeFlexibleInt(forKey: .userId)
        performedAt = container.decodeFlexibleDate(forKey: .performedAt)
        mileage = container.decodeFlexibleInt(forKey: .mileage)
        description = container.decodeFlexibleString(forKey: .description) ?? "Servisní záznam"
        price = container.decodeFlexibleDouble(forKey: .price)
        note = container.decodeFlexibleString(forKey: .note)
        category = container.decodeFlexibleString(forKey: .category)
        attachments = container.decodeFlexibleString(forKey: .attachments)
        nextServiceDueDate = container.decodeFlexibleDate(forKey: .nextServiceDueDate)
        createdByAI = container.decodeFlexibleBool(forKey: .createdByAI) ?? false
    }
}

struct Reminder: Codable, Identifiable, Hashable {
    let id: Int?
    let type: String
    let vehicleId: Int?
    let vehicleName: String?
    let text: String
    let dueDate: Date?
    let notifyAt: Date?
    let notificationMethod: String?
    let isManual: Bool
    let isCompleted: Bool?

    enum CodingKeys: String, CodingKey {
        case id
        case type
        case vehicleId
        case vehicleName
        case text
        case dueDate
        case notifyAt
        case notificationMethod
        case isManual
        case isCompleted
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = container.decodeFlexibleInt(forKey: .id)
        type = container.decodeFlexibleString(forKey: .type) ?? "VLASTNI"
        vehicleId = container.decodeFlexibleInt(forKey: .vehicleId)
        vehicleName = container.decodeFlexibleString(forKey: .vehicleName)
        text = container.decodeFlexibleString(forKey: .text) ?? "Připomínka"
        dueDate = container.decodeFlexibleDate(forKey: .dueDate)
        notifyAt = container.decodeFlexibleDate(forKey: .notifyAt)
        notificationMethod = container.decodeFlexibleString(forKey: .notificationMethod)
        isManual = container.decodeFlexibleBool(forKey: .isManual) ?? (id != nil)
        isCompleted = container.decodeFlexibleBool(forKey: .isCompleted)
    }
}

struct AnalyticsSummary: Codable {
    let scope: String
    let vehicleId: Int?
    let totalRecords: Int
    let pricedRecords: Int
    let totalCostCzk: Double
    let averageCostCzk: Double?
    let latestServiceAt: Date?
}

struct MonthlyCosts: Codable {
    let scope: String
    let vehicleId: Int?
    let months: Int
    let generatedAt: Date
    let totalRecords: Int
    let pricedRecords: Int
    let totalCostCzk: Double
    let entries: [MonthlyCostEntry]
}

struct MonthlyCostEntry: Codable, Identifiable {
    var id: String { month }
    let month: String
    let label: String
    let recordsCount: Int
    let pricedRecordsCount: Int
    let totalCostCzk: Double
}

struct LicenseStatus: Codable {
    let tenantId: String
    let plan: String
    let status: String
    let vehiclesLimit: Int
    let vehiclesCurrent: Int
    let vehiclesCurrentUser: Int?
    let vehiclesRemaining: Int?
    let isUnlimited: Bool
}

struct SystemNotification: Codable, Identifiable, Hashable {
    let id: Int
    let title: String
    let message: String
    let severity: String
    let targetType: String?
    let targetValue: String?
    let createdAt: Date?
    let expiresAt: Date?
}

struct SystemNotificationsResponse: Codable {
    let items: [SystemNotification]
    let count: Int
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

    func decodeFlexibleDate(forKey key: K) -> Date? {
        if let date = try? decodeIfPresent(Date.self, forKey: key) {
            return date
        }
        if let value = decodeFlexibleString(forKey: key) {
            return parseDate(value)
        }
        if let timestamp = try? decodeIfPresent(Double.self, forKey: key) {
            return Date(timeIntervalSince1970: timestamp)
        }
        if let timestamp = try? decodeIfPresent(Int.self, forKey: key) {
            return Date(timeIntervalSince1970: Double(timestamp))
        }
        return nil
    }

    private func parseDate(_ value: String) -> Date? {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(secondsFromGMT: 0)

        let formats = [
            "yyyy-MM-dd'T'HH:mm:ss.SSSSSS",
            "yyyy-MM-dd'T'HH:mm:ss.SSS",
            "yyyy-MM-dd'T'HH:mm:ss",
            "yyyy-MM-dd"
        ]

        for format in formats {
            formatter.dateFormat = format
            if let parsed = formatter.date(from: value) {
                return parsed
            }
        }

        return ISO8601DateFormatter().date(from: value)
    }
}
