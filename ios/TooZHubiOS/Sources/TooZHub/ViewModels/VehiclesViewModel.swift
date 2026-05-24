import Foundation

@MainActor
final class VehiclesViewModel: ObservableObject {
    @Published var isLoading = false
    @Published var error: String?
    @Published var vehicles: [Vehicle] = []

    private let service: VehicleService
    private let featureService: UserFeatureService
    private var hasLoadedOnce = false
    private var lastLoadedAt: Date?
    private let reloadTTL: TimeInterval = 45

    init(service: VehicleService, featureService: UserFeatureService) {
        self.service = service
        self.featureService = featureService
    }

    func loadIfNeeded(token: String, force: Bool = false) async {
        if !force,
           hasLoadedOnce,
           let lastLoadedAt,
           Date().timeIntervalSince(lastLoadedAt) < reloadTTL {
            return
        }
        await load(token: token)
    }

    func load(token: String) async {
        isLoading = true
        error = nil
        defer { isLoading = false }

        do {
            vehicles = try await service.fetchVehicles(token: token)
            hasLoadedOnce = true
            lastLoadedAt = Date()
        } catch {
            self.error = UserFacingErrorMapper.message(
                for: error,
                context: .account,
                fallback: "Vozidla se nepodařilo načíst."
            )
        }
    }

    func createVehicle(_ request: VehicleCreateRequest, token: String) async throws {
        do {
            _ = try await featureService.createVehicle(request, token: token)
            await loadIfNeeded(token: token, force: true)
            self.error = nil
        } catch {
            self.error = UserFacingErrorMapper.message(
                for: error,
                context: .account,
                fallback: "Vozidlo se nepodařilo uložit."
            )
            throw error
        }
    }

    func updateVehicle(id: Int, request: VehicleCreateRequest, token: String) async throws {
        do {
            _ = try await featureService.updateVehicle(id: id, request, token: token)
            await loadIfNeeded(token: token, force: true)
            self.error = nil
        } catch {
            self.error = UserFacingErrorMapper.message(
                for: error,
                context: .account,
                fallback: "Změny vozidla se nepodařilo uložit."
            )
            throw error
        }
    }

    func removeVehicleFromAccount(id: Int, reasonCode: String, followup: [String: String], token: String) async throws -> VehicleRemovalConfirmResponse {
        let response = try await featureService.removeVehicleFromAccount(
            id: id,
            reasonCode: reasonCode,
            followupAnswer: followup,
            token: token
        )
        await loadIfNeeded(token: token, force: true)
        self.error = nil
        return response
    }
}
