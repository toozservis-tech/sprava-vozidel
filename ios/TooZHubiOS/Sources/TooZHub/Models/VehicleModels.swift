import Foundation

struct Vehicle: Codable, Identifiable, Hashable {
    let id: Int
    let userEmail: String
    var nickname: String?
    var brand: String?
    var model: String?
    var year: Int?
    var engine: String?
    var vin: String?
    var plate: String?
    var orvNumber: String?
    var orvScanSource: String?
    var orvFrontImagePath: String?
    var orvBackImagePath: String?
    var orvScannedAt: Date?
    var orvConfidenceJson: String?
    var dataTrustState: String?
    var notes: String?
    var photoPath: String?
    var stkValidUntil: Date?
    var currentMileageKm: Int?
    var lastStkMileageKm: Int?
    var mileageCheckedAt: Date?
    var latestStkOdometerKm: Int?
    var latestStkOdometerDate: Date?
    var latestStkSyncAt: Date?
    var latestStkSource: String?
    var latestStkImportStatus: String?
    var tyresInfo: String?
    var insuranceProvider: String?
    var insuranceValidUntil: Date?
    var currentOwnerSince: Date?
    var tenantId: Int?
    let createdAt: Date

    var displayName: String {
        let name = [brand, model].compactMap { $0 }.joined(separator: " ")
        if !name.isEmpty { return name }
        return nickname ?? "Vehicle #\(id)"
    }

    var hasUserPhoto: Bool {
        guard let photoPath else { return false }
        return !photoPath.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    var preferredMileageKm: Int? {
        currentMileageKm ?? latestStkOdometerKm ?? lastStkMileageKm
    }

    var preferredStkMileageKm: Int? {
        latestStkOdometerKm ?? lastStkMileageKm
    }

    var normalizedBrandKey: String {
        (brand ?? "")
            .folding(options: .diacriticInsensitive, locale: Locale(identifier: "cs_CZ"))
            .lowercased()
            .replacingOccurrences(of: "[^a-z0-9]+", with: "", options: .regularExpression)
    }

    var brandMonogram: String {
        let preferred = [brand, model]
            .compactMap { $0?.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
            .joined(separator: " ")
        let source = preferred.isEmpty ? displayName : preferred
        let letters = source
            .split(separator: " ")
            .prefix(2)
            .compactMap(\.first)
            .map { String($0).uppercased() }
            .joined()
        return letters.isEmpty ? "VZ" : letters
    }
}

struct VehicleCreateRequest: Encodable {
    var nickname: String
    var brand: String?
    var model: String?
    var year: Int?
    var engine: String?
    var vin: String?
    var plate: String?
    var notes: String?
    var stkValidUntil: String
    var currentMileageKm: Int?
    var lastStkMileageKm: Int?
    var tyresInfo: String?
    var insuranceProvider: String?
    var insuranceValidUntil: String?
    var orvScanId: Int?
    var orvNumber: String?
    var orvUseOwnerData: Bool?
    var dataTrustState: String?
}

struct VehicleUpdateRequest: Encodable {
    var nickname: String?
    var brand: String?
    var model: String?
    var year: Int?
    var engine: String?
    var vin: String?
    var plate: String?
    var notes: String?
    var stkValidUntil: String?
    var currentMileageKm: Int?
    var lastStkMileageKm: Int?
    var tyresInfo: String?
    var insuranceProvider: String?
    var insuranceValidUntil: String?
    var orvScanId: Int?
    var orvNumber: String?
    var orvUseOwnerData: Bool?
    var dataTrustState: String?
}

struct ORVParseRequest: Encodable {
    let frontImageBase64: String
    let backImageBase64: String
    let frontImageMimeType: String
    let backImageMimeType: String
    let source: String
}

struct ORVParseResponse: Decodable {
    let scanId: Int
    let trustState: String
    let vehicleFields: ORVParsedVehicleFields
    let ownerFields: ORVParsedOwnerFields
    let confidence: [ORVFieldConfidence]
    let warnings: [String]
    let missingFields: [String]
}

struct ORVParsedVehicleFields: Decodable {
    let plate: String?
    let vin: String?
    let brand: String?
    let model: String?
    let typeLabel: String?
    let variant: String?
    let version: String?
    let commercialName: String?
    let category: String?
    let vehicleKind: String?
    let fuel: String?
    let enginePowerKw: String?
    let engineDisplacementCc: String?
    let firstRegistrationDate: String?
    let firstRegistrationCzDate: String?
    let seatsCount: String?
    let maxSpeedKmh: String?
    let emissions: String?
    let consumption: String?
    let weights: String?
    let orvNumber: String?
}

struct ORVParsedOwnerFields: Decodable {
    let ownerName: String?
    let ownerIdentifier: String?
    let ownerAddress: String?
    let operatorName: String?
    let operatorIdentifier: String?
    let operatorAddress: String?
}

struct ORVFieldConfidence: Decodable, Hashable {
    let fieldName: String
    let confidence: Double
    let state: String
}

enum VehicleInputValidator {
    private static let allowedVINCharacters = CharacterSet(charactersIn: "ABCDEFGHJKLMNPRSTUVWXYZ0123456789")

    static func normalizedVIN(_ raw: String) -> String {
        raw
            .uppercased()
            .unicodeScalars
            .filter { CharacterSet.alphanumerics.contains($0) }
            .map(String.init)
            .joined()
    }

    static func isValidVIN(_ raw: String) -> Bool {
        let normalized = normalizedVIN(raw)
        guard normalized.count == 17 else { return false }
        return normalized.unicodeScalars.allSatisfy { allowedVINCharacters.contains($0) }
    }

    static func validationMessage(for raw: String, required: Bool) -> String? {
        let normalized = normalizedVIN(raw)
        if normalized.isEmpty {
            return required ? "VIN je povinný. Doplňte jej před pokračováním." : nil
        }
        if normalized.count != 17 {
            return "VIN musí mít přesně 17 znaků."
        }
        if !isValidVIN(normalized) {
            return "VIN obsahuje nepovolené znaky. Použijte pouze písmena a čísla bez I, O a Q."
        }
        return nil
    }
}

struct TachometerChallengeResponse: Decodable {
    let challengeId: String
    let captchaImageBase64: String
    let captchaMimeType: String
    let expiresInSeconds: Int
}

struct TachometerChallengeRequestBody: Encodable {
    let vin: String?
}

struct TachometerLookupRequestBody: Encodable {
    let challengeId: String
    let vin: String
    let captchaCode: String
}

struct TachometerInspection: Decodable {
    let checkDate: Date?
    let mileageKm: Int
    let protocolNumber: String?
    let inspectionType: String?
}

struct TachometerLookupResponse: Decodable {
    let vin: String
    let latestMileageKm: Int
    let latestCheckDate: Date?
    let inspections: [TachometerInspection]
    let source: String
}

struct VehicleTachometerInitResponse: Decodable {
    let sessionId: String
    let captchaImageBase64: String
    let captchaMimeType: String
    let expiresInSeconds: Int
}

struct VehicleTachometerSubmitRequest: Encodable {
    let sessionId: String
    let captchaCode: String
}

struct VehicleTachometerSubmitResponse: Decodable {
    let vehicle: Vehicle
    let latestMileageKm: Int
    let latestCheckDate: Date?
    let inspections: [TachometerInspection]
    let createdRecordId: Int
    let source: String
}

struct VehicleMileageRecordRequest: Encodable {
    let mileageKm: Int
    let note: String?
    let confirmLowerThanCurrent: Bool
}

struct VehicleMileageRecordResponse: Decodable {
    let vehicle: Vehicle
    let createdRecordId: Int
}

struct VehiclePhotoUploadRequest: Encodable {
    let fileName: String
    let fileMimeType: String
    let fileContentBase64: String
}

struct VehiclePhotoUploadResponse: Decodable {
    let message: String?
    let photoPath: String?
    let photoURL: String?
}

struct VehicleInspectionHistoryEntry: Identifiable, Hashable {
    let id: Int
    let checkDate: Date?
    let mileageKm: Int?
    let source: String?
    let status: String?
    let protocolNumber: String?
    let inspectionType: String?
    let summary: String?
    let hasDocuments: Bool
    let documentsCount: Int
    let documents: [VehicleInspectionHistoryDocument]

    init(
        id: Int,
        checkDate: Date?,
        mileageKm: Int?,
        source: String?,
        status: String?,
        protocolNumber: String?,
        inspectionType: String?,
        summary: String?,
        hasDocuments: Bool,
        documentsCount: Int,
        documents: [VehicleInspectionHistoryDocument]
    ) {
        self.id = id
        self.checkDate = checkDate
        self.mileageKm = mileageKm
        self.source = source
        self.status = status
        self.protocolNumber = protocolNumber
        self.inspectionType = inspectionType
        self.summary = summary
        self.hasDocuments = hasDocuments
        self.documentsCount = documentsCount
        self.documents = documents
    }
}

struct VehicleInspectionHistoryDocument: Identifiable, Hashable {
    let id: String
    let title: String
    let documentType: String
    let available: Bool
    let openMode: String
    let reason: String?
    let externalURL: String?
    let internalProxyURL: String?
}

// MARK: - Vehicle removal (archival / handover)

struct VehicleRemovalTransferPayload: Codable, Hashable {
    let token: String?
    let qrPayload: String?
}

struct VehicleRemovalConfirmResponse: Codable, Hashable {
    let removed: Bool?
    let vehicleId: Int?
    let reasonCode: String?
    let digitalReportDocumentId: Int?
    let digitalReportDocumentUid: String?
    let digitalReportUrl: String?
    let archiveBundlePath: String?
    let transfer: VehicleRemovalTransferPayload?
    let historyPreserved: Bool?
}

