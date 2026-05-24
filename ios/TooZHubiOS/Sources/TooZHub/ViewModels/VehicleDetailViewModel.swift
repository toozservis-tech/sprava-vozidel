import Foundation

@MainActor
final class VehicleDetailViewModel: ObservableObject {
    @Published var isLoading = false
    @Published var primaryLoading = false
    @Published var secondaryLoading = false
    @Published var error: String?
    @Published var vehicle: Vehicle?
    @Published var records: [ServiceRecord] = []
    @Published var tachometerHistory: [VehicleInspectionHistoryEntry] = []
    @Published var tachometerHistoryErrorMessage: String?
    @Published var isSavingMileage = false
    @Published var isUpdatingVehiclePhoto = false

    private let service: VehicleService
    private let featureService: UserFeatureService

    private let primaryTTL: TimeInterval = 45
    private let secondaryTTL: TimeInterval = 90

    private var primaryCache: [Int: CacheEntry<Vehicle>] = [:]
    private var secondaryCache: [Int: CacheEntry<[ServiceRecord]>] = [:]

    private var activeVehicleId: Int?
    private var activePrimaryRequestKey: RequestKey?
    private var activeSecondaryRequestKey: RequestKey?

    init(service: VehicleService, featureService: UserFeatureService) {
        self.service = service
        self.featureService = featureService
    }

    func load(vehicleId: Int, token: String) async {
        await load(vehicleId: vehicleId, token: token, forceRefresh: false)
    }

    func addRecord(vehicleId: Int, request: ServiceRecordCreateRequest, token: String) async {
        do {
            _ = try await featureService.createServiceRecord(vehicleId: vehicleId, request, token: token)
            await load(vehicleId: vehicleId, token: token, forceRefresh: true)
        } catch {
            self.error = userFacingMessage(for: error, context: .save)
        }
    }

    func updateRecord(vehicleId: Int, recordId: Int, request: ServiceRecordUpdateRequest, token: String) async {
        do {
            _ = try await featureService.updateServiceRecord(vehicleId: vehicleId, recordId: recordId, request, token: token)
            await load(vehicleId: vehicleId, token: token, forceRefresh: true)
        } catch {
            self.error = userFacingMessage(for: error, context: .save)
        }
    }

    func deleteRecord(vehicleId: Int, recordId: Int, token: String) async {
        do {
            try await featureService.deleteServiceRecord(vehicleId: vehicleId, recordId: recordId, token: token)
            await load(vehicleId: vehicleId, token: token, forceRefresh: true)
        } catch {
            self.error = userFacingMessage(for: error, context: .save)
        }
    }

    func recordMileage(
        vehicleId: Int,
        mileageKm: Int,
        note: String?,
        confirmLowerThanCurrent: Bool,
        token: String
    ) async throws {
        isSavingMileage = true
        defer { isSavingMileage = false }

        do {
            let response = try await service.recordMileage(
                vehicleId: vehicleId,
                request: VehicleMileageRecordRequest(
                    mileageKm: mileageKm,
                    note: note,
                    confirmLowerThanCurrent: confirmLowerThanCurrent
                ),
                token: token
            )

            vehicle = response.vehicle
            primaryCache[vehicleId] = CacheEntry(value: response.vehicle, loadedAt: Date())
            await load(vehicleId: vehicleId, token: token, forceRefresh: true)
        } catch let apiError as APIError {
            if shouldUseLegacyMileageFallback(for: apiError) {
                let updated = try await featureService.updateVehiclePartial(
                    id: vehicleId,
                    VehicleUpdateRequest(currentMileageKm: mileageKm),
                    token: token
                )
                vehicle = updated
                primaryCache[vehicleId] = CacheEntry(value: updated, loadedAt: Date())
                error = nil
                return
            }
            throw apiError
        }
    }

    func initVehicleTachometer(vehicleId: Int, token: String) async throws -> VehicleTachometerInitResponse {
        try await service.initVehicleTachometer(vehicleId: vehicleId, token: token)
    }

    func submitVehicleTachometer(
        vehicleId: Int,
        sessionId: String,
        captchaCode: String,
        token: String
    ) async throws -> VehicleTachometerSubmitResponse {
        let response = try await service.submitVehicleTachometer(
            vehicleId: vehicleId,
            sessionId: sessionId,
            captchaCode: captchaCode,
            token: token
        )
        vehicle = response.vehicle
        primaryCache[vehicleId] = CacheEntry(value: response.vehicle, loadedAt: Date())
        await loadSecondaryIfNeeded(vehicleId: vehicleId, token: token, forceRefresh: true)
        return response
    }

    func uploadVehiclePhoto(
        vehicleId: Int,
        imageData: Data,
        fileName: String,
        mimeType: String,
        token: String
    ) async throws {
        isUpdatingVehiclePhoto = true
        defer { isUpdatingVehiclePhoto = false }

        let request = VehiclePhotoUploadRequest(
            fileName: fileName,
            fileMimeType: mimeType,
            fileContentBase64: imageData.base64EncodedString()
        )
        _ = try await service.uploadVehiclePhoto(vehicleId: vehicleId, request: request, token: token)
        let detail = try await service.fetchVehicleDetail(id: vehicleId, token: token)
        vehicle = detail
        primaryCache[vehicleId] = CacheEntry(value: detail, loadedAt: Date())
    }

    func deleteVehiclePhoto(vehicleId: Int, token: String) async throws {
        isUpdatingVehiclePhoto = true
        defer { isUpdatingVehiclePhoto = false }

        try await service.deleteVehiclePhoto(vehicleId: vehicleId, token: token)
        let detail = try await service.fetchVehicleDetail(id: vehicleId, token: token)
        vehicle = detail
        primaryCache[vehicleId] = CacheEntry(value: detail, loadedAt: Date())
    }

    private func load(vehicleId: Int, token: String, forceRefresh: Bool) async {
        activeVehicleId = vehicleId
        error = nil
        tachometerHistoryErrorMessage = nil

        let primaryReady = await loadPrimaryIfNeeded(
            vehicleId: vehicleId,
            token: token,
            forceRefresh: forceRefresh
        )

        guard primaryReady, activeVehicleId == vehicleId else { return }

        // Give SwiftUI one render turn after the hero payload arrives.
        await Task.yield()

        await loadSecondaryIfNeeded(
            vehicleId: vehicleId,
            token: token,
            forceRefresh: forceRefresh
        )
    }

    func loadPrimaryIfNeeded(vehicleId: Int, token: String, forceRefresh: Bool = false) async -> Bool {
        let requestKey = RequestKey(vehicleId: vehicleId, token: token)

        if !forceRefresh, let cached = cachedPrimaryEntry(for: vehicleId) {
            vehicle = cached.value
            isLoading = false
            primaryLoading = false
            PerformanceLog.mark("primary fetch cache-hit vehicleId=\(vehicleId)")
            return true
        }

        if activePrimaryRequestKey == requestKey, primaryLoading {
            return vehicle != nil
        }

        activePrimaryRequestKey = requestKey
        primaryLoading = true
        isLoading = true

        let startedAt = Date().timeIntervalSinceReferenceDate
        PerformanceLog.mark("primary fetch start vehicleId=\(vehicleId) force=\(forceRefresh)")

        defer {
            primaryLoading = false
            isLoading = false
            if activePrimaryRequestKey == requestKey {
                activePrimaryRequestKey = nil
            }
            let elapsedMs = Int((Date().timeIntervalSinceReferenceDate - startedAt) * 1000)
            PerformanceLog.mark("primary fetch end vehicleId=\(vehicleId) elapsedMs=\(elapsedMs)")
        }

        do {
            let detail = try await service.fetchVehicleDetail(id: vehicleId, token: token)
            guard activeVehicleId == vehicleId else { return false }
            vehicle = detail
            primaryCache[vehicleId] = CacheEntry(value: detail, loadedAt: Date())
            return true
        } catch {
            if vehicle == nil || forceRefresh {
                self.error = userFacingMessage(for: error, context: .load)
            }
            return vehicle != nil
        }
    }

    func loadSecondaryIfNeeded(vehicleId: Int, token: String, forceRefresh: Bool = false) async {
        guard vehicle != nil else { return }

        let requestKey = RequestKey(vehicleId: vehicleId, token: token)

        if !forceRefresh, let cached = cachedSecondaryEntry(for: vehicleId) {
            records = cached.value
            secondaryLoading = false
            PerformanceLog.mark("secondary fetch cache-hit vehicleId=\(vehicleId) records=\(cached.value.count)")
            return
        }

        if activeSecondaryRequestKey == requestKey, secondaryLoading {
            return
        }

        activeSecondaryRequestKey = requestKey
        secondaryLoading = true

        let startedAt = Date().timeIntervalSinceReferenceDate
        PerformanceLog.mark("secondary fetch start vehicleId=\(vehicleId) force=\(forceRefresh)")

        defer {
            secondaryLoading = false
            if activeSecondaryRequestKey == requestKey {
                activeSecondaryRequestKey = nil
            }
            let elapsedMs = Int((Date().timeIntervalSinceReferenceDate - startedAt) * 1000)
            PerformanceLog.mark("secondary fetch end vehicleId=\(vehicleId) elapsedMs=\(elapsedMs)")
        }

        do {
            let fetchedRecords = try await service.fetchServiceRecords(vehicleId: vehicleId, token: token)
            guard activeVehicleId == vehicleId else { return }
            records = fetchedRecords
            secondaryCache[vehicleId] = CacheEntry(value: fetchedRecords, loadedAt: Date())
        } catch {
            if records.isEmpty || forceRefresh {
                self.error = userFacingMessage(for: error, context: .load)
            }
        }

        do {
            let history = try await service.fetchVehicleTachometerHistory(vehicleId: vehicleId, token: token)
            guard activeVehicleId == vehicleId else { return }
            tachometerHistory = history
            tachometerHistoryErrorMessage = nil
        } catch let apiError as APIError {
            if shouldIgnoreTachometerHistoryError(apiError) {
                tachometerHistory = []
                tachometerHistoryErrorMessage = nil
            } else if forceRefresh && tachometerHistory.isEmpty {
                tachometerHistoryErrorMessage = "Historii STK se nepodařilo načíst."
            }
        } catch {
            if forceRefresh && tachometerHistory.isEmpty {
                tachometerHistoryErrorMessage = "Historii STK se nepodařilo načíst."
            }
        }
    }

    private func cachedPrimaryEntry(for vehicleId: Int) -> CacheEntry<Vehicle>? {
        guard let entry = primaryCache[vehicleId], !entry.isExpired(ttl: primaryTTL) else { return nil }
        return entry
    }

    private func cachedSecondaryEntry(for vehicleId: Int) -> CacheEntry<[ServiceRecord]>? {
        guard let entry = secondaryCache[vehicleId], !entry.isExpired(ttl: secondaryTTL) else { return nil }
        return entry
    }

    private func shouldUseLegacyMileageFallback(for error: APIError) -> Bool {
        guard case let .serverError(message) = error else { return false }
        let normalized = message.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return normalized == "not found" || normalized.contains("404")
    }

    private func shouldIgnoreTachometerHistoryError(_ error: APIError) -> Bool {
        switch error {
        case .serverError(let message):
            let normalized = message.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            return normalized == "not found" || normalized.contains("404")
        default:
            return false
        }
    }

    private func userFacingMessage(for error: Error, context: ErrorContext) -> String {
        switch context {
        case .load:
            return UserFacingErrorMapper.message(
                for: error,
                context: .vehicleDetailLoad,
                fallback: "Detail vozidla se nepodařilo načíst."
            )
        case .save:
            return UserFacingErrorMapper.message(
                for: error,
                context: .vehicleDetailSave,
                fallback: "Změny vozidla se nepodařilo uložit."
            )
        }
    }
}

private extension VehicleDetailViewModel {
    enum ErrorContext {
        case load
        case save
    }

    struct CacheEntry<Value> {
        let value: Value
        let loadedAt: Date

        func isExpired(ttl: TimeInterval, now: Date = Date()) -> Bool {
            now.timeIntervalSince(loadedAt) > ttl
        }
    }

    struct RequestKey: Equatable {
        let vehicleId: Int
        let token: String
    }

    enum PerformanceLog {
        static func mark(_ message: String) {
#if DEBUG
            print("[VehicleDetailViewModelPerformance] \(message)")
#endif
        }
    }
}
