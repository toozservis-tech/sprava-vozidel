import Foundation

struct ServiceRecordCreateRequest: Encodable {
    let performedAt: Date
    let mileage: Int?
    let description: String
    let price: Double?
    let note: String?
    let category: String
    let attachments: String?
    let nextServiceDueDate: String?
}

struct ServiceRecordUpdateRequest: Encodable {
    let performedAt: Date?
    let mileage: Int?
    let description: String?
    let price: Double?
    let note: String?
    let category: String?
    let attachments: String?
    let nextServiceDueDate: String?
}

struct ServiceRecordAttachmentUploadRequest: Encodable {
    let fileName: String
    let fileMimeType: String
    let fileContentBase64: String
}

struct ServiceRecordAttachmentUploadResponse: Decodable {
    let fileName: String
    let mimeType: String
    let fileSize: Int?
    let storageKey: String
    let downloadURL: String

    enum CodingKeys: String, CodingKey {
        case fileName = "file_name"
        case mimeType = "mime_type"
        case fileSize = "file_size"
        case storageKey = "storage_key"
        case downloadURL = "download_url"
    }
}

struct ServiceRecordDocumentPrefillRequest: Encodable {
    let sourceType: String
    let fileName: String
    let fileMimeType: String
    let fileContentBase64: String
    let manualText: String?
    let manualNote: String?
    let fallbackCategory: String?
    let fallbackMileage: Int?
    let fallbackPerformedAt: Date?
    let fallbackDescription: String?
    let fallbackPrice: Double?
}

struct ServiceRecordDocumentPrefillResponse: Decodable {
    let processingStatus: String?
    let parseConfidence: Double?
    let parsedData: ServiceRecordParsedDocumentData?
    let prefill: ServiceRecordDocumentPrefillData?
    let extractionEngine: String?
    let extractionWarning: String?
}

struct ServiceRecordParsedDocumentData: Decodable {
    let documentNumber: String?
    let supplierName: String?
    let supplierEmail: String?
    let serviceSummary: String?
    let technicianName: String?
    let confidence: Double?
}

struct ServiceRecordDocumentPrefillData: Decodable {
    let performedAt: Date?
    let mileage: Int?
    let description: String?
    let price: Double?
    let note: String?
    let category: String?
    let serviceReport: ServiceReportPayload?
}

struct ServiceReportPayload: Codable {
    let sourceType: String?
    let documentNumber: String?
    let supplierName: String?
    let supplierEmail: String?
    let supplierWebsite: String?
    let serviceLink: String?
    let customerName: String?
    let serviceSummary: String?
    let issueDescription: String?
    let technicianName: String?
    let technicianInitials: String?
    let issueDate: String?
    let dueDate: String?
    let currency: String?
    let laborHours: Double?
    let laborHourRate: Double?
    let laborTotal: Double?
    let materialsTotal: Double?
    let subtotalWithoutVat: Double?
    let vatRate: Double?
    let vatAmount: Double?
    let totalWithVat: Double?
    let items: [ServiceReportItemPayload]?
}

struct ServiceReportItemPayload: Codable {
    let name: String
    let quantity: Double?
    let unit: String?
    let unitPrice: Double?
    let totalPrice: Double?
    let currency: String?
}

struct ReminderCreateRequest: Encodable {
    let vehicleId: Int?
    let type: String
    let text: String
    let dueDate: String?
    let notifyAt: Date?
    let notificationMethod: String?
    let repeatCount: Int?
    let repeatIntervalDays: Int?
}

struct ReminderUpdateRequest: Encodable {
    let type: String?
    let vehicleId: Int?
    let text: String?
    let dueDate: String?
    let notifyAt: Date?
    let notificationMethod: String?
    let isCompleted: Bool?
}

struct ReminderSettings: Codable {
    let enabled: Bool
    let notification: ReminderNotificationSettings
}

struct ReminderNotificationSettings: Codable {
    let notificationMethod: String
    let notifyDaysBefore: Int
}

struct ReminderSettingsUpdateRequest: Encodable {
    let enabled: Bool
    let notification: ReminderNotificationSettingsUpdateRequest
}

struct ReminderNotificationSettingsUpdateRequest: Encodable {
    let notificationMethod: String
    let notifyDaysBefore: Int
}

struct VehicleAccessGrantRequest: Encodable {
    let vehicleId: Int
    let serviceId: Int
    let note: String?
    let conflictStrategy: String
}

struct VehicleAccessGrant: Codable, Identifiable, Hashable {
    var id: String { "\(serviceId)-\(vehicleId)" }
    let serviceId: Int
    let vehicleId: Int
    let customerId: Int
    let serviceName: String
    let serviceEmail: String
    let vehicleName: String?
    let vehiclePlate: String?
    let status: String?
    let updatedAt: String?
}

struct VehicleAccessGrantListResponse: Codable {
    let grants: [VehicleAccessGrant]
}

struct ServiceAccessRequest: Codable, Identifiable, Hashable {
    let id: Int
    let vehicleId: Int
    let serviceId: Int
    let serviceName: String
    let serviceEmail: String?
    let vehicleName: String?
    let vehiclePlate: String?
    let requestedAt: String?
    let status: String
    let note: String?
    let scopeSummary: String?
}

struct ServiceAccessRequestListResponse: Codable {
    let requests: [ServiceAccessRequest]
}

struct ServiceAccessRequestDecisionRequest: Encodable {
    let decision: String
    let note: String?
}

struct ServiceContactsResponse: Decodable {
    let services: [ServiceContact]

    enum CodingKeys: String, CodingKey {
        case services
    }

    init(services: [ServiceContact]) {
        self.services = services
    }

    init(from decoder: Decoder) throws {
        if let container = try? decoder.container(keyedBy: CodingKeys.self) {
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
            services = direct
            return
        }
        if let nested = try? [[ServiceContact]](from: decoder) {
            services = nested.flatMap { $0 }
            return
        }

        services = []
    }
}

struct ChangePasswordRequest: Encodable {
    let currentPassword: String
    let newPassword: String
}

struct SupportRequest: Encodable {
    let category: String
    let subject: String
    let message: String
    let phone: String?
    let includeDiagnostics: Bool
    let pageUrl: String?
    let userAgent: String?
}

struct DeleteAccountRequest: Encodable {
    let currentPassword: String
    let confirmationText: String
    let exportDownloaded: Bool
}
