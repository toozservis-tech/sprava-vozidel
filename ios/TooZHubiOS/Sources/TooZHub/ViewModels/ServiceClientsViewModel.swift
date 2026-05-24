import Foundation

@MainActor
final class ServiceClientsViewModel: ObservableObject {
    enum LoadState: Equatable {
        case idle
        case serviceAccessReady
        case legacyWorkspaceReady
        case backendUnavailable
    }

    enum LookupState: Equatable {
        case idle
        case found
        case pendingRequest
        case alreadyApproved
        case notFound
    }

    @Published var approvedVehicles: [ServiceApprovedVehicleSummary] = []
    @Published var customers: [ServiceWorkspaceCustomer] = []
    @Published var selectedCustomerVehicles: [ServiceWorkspaceVehicle] = []
    @Published var selectedCustomerId: Int?
    @Published var lookupQuery = ""
    @Published var lookupResults: [ServiceVehicleLookupCandidate] = []
    @Published var loadState: LoadState = .idle
    @Published var lookupState: LookupState = .idle
    @Published var isLookupLoading = false
    @Published var lookupError: String?
    @Published var isLoading = false
    @Published var error: String?

    private let service: ServiceWorkspaceService

    init(service: ServiceWorkspaceService) {
        self.service = service
    }

    func load(token: String) async {
        isLoading = true
        error = nil
        defer { isLoading = false }

        do {
            let backendMode = try await service.detectBackendMode(token: token)
            switch backendMode {
            case .serviceAccessModel:
                approvedVehicles = try await service.fetchApprovedVehicles(token: token).items
                customers = []
                selectedCustomerVehicles = []
                selectedCustomerId = nil
                loadState = .serviceAccessReady
            case .legacyWorkspace:
                approvedVehicles = []
                customers = try await service.fetchCustomers(token: token)
                if selectedCustomerId == nil {
                    selectedCustomerId = customers.first?.customerId
                }
                if let selectedCustomerId {
                    selectedCustomerVehicles = try await service.fetchCustomerVehicles(customerId: selectedCustomerId, token: token)
                } else {
                    selectedCustomerVehicles = []
                }
                loadState = .legacyWorkspaceReady
            case .unavailable:
                approvedVehicles = []
                customers = []
                selectedCustomerVehicles = []
                selectedCustomerId = nil
                loadState = .backendUnavailable
                error = nil
            }
        } catch is CancellationError {
            error = nil
            return
        } catch {
            approvedVehicles = []
            customers = []
            selectedCustomerVehicles = []
            if isRouteNotDeployed(error) {
                loadState = .backendUnavailable
                self.error = nil
            } else {
                loadState = .idle
                self.error = localizedApprovedVehiclesLoadError(error)
            }
        }
    }

    func selectCustomer(_ customerId: Int, token: String) async {
        selectedCustomerId = customerId
        do {
            selectedCustomerVehicles = try await service.fetchCustomerVehicles(customerId: customerId, token: token)
        } catch is CancellationError {
            return
        } catch {
            self.error = localizedApprovedVehiclesLoadError(error)
        }
    }

    func lookupVehicle(token: String) async {
        let query = lookupQuery.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !query.isEmpty else {
            lookupError = "Zadejte SPZ nebo VIN vozidla."
            lookupResults = []
            lookupState = .idle
            return
        }

        isLookupLoading = true
        lookupError = nil
        defer { isLookupLoading = false }

        do {
            lookupResults = try await service.lookupVehicle(query: query, token: token).candidates
            if let first = lookupResults.first {
                lookupState = lookupState(for: first.status)
            } else {
                lookupState = .notFound
                lookupError = "Pro zadanou SPZ nebo VIN jsme zatím nenašli kandidáta vozidla."
            }
        } catch is CancellationError {
            return
        } catch {
            lookupResults = []
            lookupState = .idle
            lookupError = isRouteNotDeployed(error)
                ? "Vyhledání vozidla zatím není na tomto serveru dostupné. Počkejte na nasazení nového servisního přístupu."
                : localizedLookupError(error)
        }
    }

    func sendAccessRequest(candidate: ServiceVehicleLookupCandidate, note: String?, token: String) async throws -> String {
        let response = try await service.createAccessRequest(
            ServiceAccessRequestCreateRequest(
                vehicleId: candidate.vehicleId,
                lookupQuery: lookupQuery.trimmingCharacters(in: .whitespacesAndNewlines),
                note: note
            ),
            token: token
        )
        return response.message?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false
            ? response.message!
            : "Žádost o přístup byla odeslaná. Vozidlo uvidíte až po schválení uživatelem."
    }

    private func localizedLookupError(_ error: Error) -> String {
        return UserFacingErrorMapper.message(
            for: error,
            context: .account,
            fallback: "Vyhledání vozidla se nepodařilo. Zkuste to prosím znovu."
        )
    }

    private func localizedApprovedVehiclesLoadError(_ error: Error) -> String {
        UserFacingErrorMapper.message(
            for: error,
            context: .account,
            fallback: "Schválená vozidla se nepodařilo načíst. Zkuste to prosím znovu."
        )
    }

    private func isRouteNotDeployed(_ error: Error) -> Bool {
        switch error {
        case APIError.serverError(let message), APIError.transportError(let message):
            let lowered = message.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            return lowered == "not found" || lowered.contains("404")
        default:
            let lowered = error.localizedDescription.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            return lowered == "not found" || lowered.contains("404")
        }
    }

    private func lookupState(for status: String) -> LookupState {
        switch status {
        case "pending_request":
            return .pendingRequest
        case "already_approved":
            return .alreadyApproved
        case "matched":
            return .found
        default:
            return .found
        }
    }
}
