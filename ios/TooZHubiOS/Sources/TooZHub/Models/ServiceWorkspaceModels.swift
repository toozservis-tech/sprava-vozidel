import Foundation

struct ServiceWorkspaceCustomer: Codable, Identifiable, Hashable {
    var id: Int { customerId }
    let customerId: Int
    let email: String
    let name: String?
    let phone: String?
    let vehiclesCount: Int
    let sharedVehiclesCount: Int
    let lastServiceDate: String?
    let note: String?
    let createdAt: String?
}

struct ServiceWorkspaceVehicle: Codable, Identifiable, Hashable {
    let id: Int
    let nickname: String?
    let brand: String?
    let model: String?
    let year: Int?
    let plate: String?
    let vin: String?
    let stkValidUntil: String?
    let currentMileageKm: Int?
    let lastStkMileageKm: Int?
    let mileageCheckedAt: String?
    let createdAt: String?
    let isShared: Bool

    var displayName: String {
        let composed = [brand, model].compactMap { $0 }.joined(separator: " ")
        if !composed.isEmpty { return composed }
        return nickname ?? "Vehicle #\(id)"
    }
}

struct ServiceVehicleContext: Identifiable, Hashable {
    enum Source: String, Hashable {
        case approvedAccess
        case legacyWorkspace
    }

    let id: Int
    let title: String
    let subtitle: String?
    let plate: String?
    let vin: String?
    let customerName: String?
    let approvedAtLabel: String?
    let currentMileageKm: Int?
    let stkValidUntil: String?
    let source: Source

    init(approvedVehicle: ServiceApprovedVehicleSummary) {
        id = approvedVehicle.id
        title = approvedVehicle.displayName
        subtitle = approvedVehicle.customerName
        plate = approvedVehicle.vehiclePlate
        vin = nil
        customerName = approvedVehicle.customerName
        approvedAtLabel = approvedVehicle.lastSharedAt
        currentMileageKm = nil
        stkValidUntil = nil
        source = .approvedAccess
    }

    init(legacyVehicle: ServiceWorkspaceVehicle, customerName: String?) {
        id = legacyVehicle.id
        title = legacyVehicle.displayName
        subtitle = customerName
        plate = legacyVehicle.plate
        vin = legacyVehicle.vin
        self.customerName = customerName
        approvedAtLabel = nil
        currentMileageKm = legacyVehicle.currentMileageKm
        stkValidUntil = legacyVehicle.stkValidUntil
        source = .legacyWorkspace
    }
}

struct ServiceVehicleLookupRequest: Encodable {
    let query: String
}

struct ServiceVehicleLookupCandidate: Codable, Identifiable, Hashable {
    let id: String
    let vehicleId: Int?
    let nickname: String?
    let brand: String?
    let model: String?
    let plateMasked: String?
    let vinMasked: String?
    let city: String?
    let ownerLabel: String?
    let status: String
    let canRequestAccess: Bool

    var displayName: String {
        let composed = [brand, model].compactMap { $0 }.joined(separator: " ")
        if !composed.isEmpty { return composed }
        if let nickname, !nickname.isEmpty { return nickname }
        return "Nalezené vozidlo"
    }

    enum CodingKeys: String, CodingKey {
        case id
        case vehicleId
        case nickname
        case brand
        case model
        case plateMasked
        case vinMasked
        case city
        case ownerLabel
        case status
        case canRequestAccess
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        vehicleId = try? container.decodeIfPresent(Int.self, forKey: .vehicleId)
        nickname = try? container.decodeIfPresent(String.self, forKey: .nickname)
        brand = try? container.decodeIfPresent(String.self, forKey: .brand)
        model = try? container.decodeIfPresent(String.self, forKey: .model)
        plateMasked = try? container.decodeIfPresent(String.self, forKey: .plateMasked)
        vinMasked = try? container.decodeIfPresent(String.self, forKey: .vinMasked)
        city = try? container.decodeIfPresent(String.self, forKey: .city)
        ownerLabel = try? container.decodeIfPresent(String.self, forKey: .ownerLabel)
        status = (try? container.decodeIfPresent(String.self, forKey: .status)) ?? "pending"
        canRequestAccess = (try? container.decodeIfPresent(Bool.self, forKey: .canRequestAccess)) ?? true

        if let decodedID = try? container.decodeIfPresent(String.self, forKey: .id), !decodedID.isEmpty {
            id = decodedID
        } else if let vehicleId {
            id = "vehicle-\(vehicleId)"
        } else {
            id = [plateMasked, vinMasked, nickname, brand, model]
                .compactMap { $0?.trimmingCharacters(in: .whitespacesAndNewlines) }
                .first(where: { !$0.isEmpty }) ?? UUID().uuidString
        }
    }
}

struct ServiceVehicleLookupResponse: Codable {
    let candidates: [ServiceVehicleLookupCandidate]
}

struct ServiceAccessRequestCreateRequest: Encodable {
    let vehicleId: Int?
    let lookupQuery: String
    let note: String?
}

struct ServiceAccessRequestCreateResponse: Codable {
    let created: Bool
    let requestId: Int?
    let status: String?
    let message: String?
}

struct ServiceAccessRequestDecisionResponse: Codable {
    let resolved: Bool
    let requestId: Int?
    let decision: String?
    let vehicleId: Int?
    let serviceId: Int?
}

struct ServiceApprovedVehicleSummary: Codable, Identifiable, Hashable {
    let id: Int
    let customerId: Int?
    let customerName: String?
    let vehicleName: String?
    let vehiclePlate: String?
    let lastSharedAt: String?

    var displayName: String {
        let trimmed = vehicleName?.trimmingCharacters(in: .whitespacesAndNewlines)
        if let trimmed, !trimmed.isEmpty {
            return trimmed
        }
        return "Vozidlo #\(id)"
    }
}

struct ServiceApprovedVehicleListResponse: Codable {
    let items: [ServiceApprovedVehicleSummary]
}

struct ServiceWorkspaceReminder: Codable, Identifiable, Hashable {
    let id: Int
    let customerId: Int
    let customerName: String?
    let vehicleId: Int?
    let vehicleName: String?
    let text: String
    let type: String
    let dueDate: String?
    let isCompleted: Bool
}

struct ServiceWorkspaceVehicleCreateRequest: Encodable {
    let nickname: String
    let brand: String?
    let model: String?
    let year: Int?
    let plate: String?
    let vin: String?
    let stkValidUntil: String
    let currentMileageKm: Int?
    let lastStkMileageKm: Int?
    let engine: String?
    let notes: String?
    let orvScanId: Int?
    let orvNumber: String?
    let orvUseOwnerData: Bool?
    let dataTrustState: String?
}

struct PendingVehicleRegistrationRequest: Encodable {
    let inviteEmail: String
    let inviteName: String?
    let inviteMessage: String?
    let vehicle: ServiceWorkspaceVehicleCreateRequest
}

struct PendingVehicleRegistrationResponse: Decodable {
    let vehicleId: Int
    let customerId: Int?
    let linkedNow: Bool?
    let alreadyLinked: Bool?
    let emailSent: Bool?
    let registrationState: String?
    let registrationUrl: String?
    let message: String?
}

struct ServiceWorkspaceReminderCreateRequest: Encodable {
    let customerId: Int
    let vehicleId: Int?
    let type: String
    let text: String
    let dueDate: String?
    let notifyAt: String?
    let notificationMethod: String?
}

struct ServiceWorkspaceReminderUpdateRequest: Encodable {
    let type: String?
    let text: String?
    let dueDate: String?
    let notifyAt: String?
    let notificationMethod: String?
    let isCompleted: Bool?
}
