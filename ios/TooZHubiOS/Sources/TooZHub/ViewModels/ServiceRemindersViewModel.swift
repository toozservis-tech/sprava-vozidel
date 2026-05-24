import Foundation

@MainActor
final class ServiceRemindersViewModel: ObservableObject {
    enum LoadState: Equatable {
        case idle
        case loaded
        case backendUnavailable
    }

    @Published var reminders: [ServiceWorkspaceReminder] = []
    @Published var customers: [ServiceWorkspaceCustomer] = []
    @Published var selectedCustomerVehicles: [ServiceWorkspaceVehicle] = []
    @Published var isLoading = false
    @Published var error: String?
    @Published var loadState: LoadState = .idle

    private let service: ServiceWorkspaceService

    init(service: ServiceWorkspaceService) {
        self.service = service
    }

    func load(token: String) async {
        isLoading = true
        error = nil
        loadState = .idle
        defer { isLoading = false }

        async let remindersReq = service.fetchReminders(token: token)
        async let customersReq = service.fetchCustomers(token: token)

        var loadErrors: [Error] = []

        do {
            reminders = try await remindersReq
        } catch is CancellationError {
            return
        } catch {
            reminders = []
            loadErrors.append(error)
        }

        do {
            customers = try await customersReq
        } catch is CancellationError {
            return
        } catch {
            customers = []
            loadErrors.append(error)
        }

        if !reminders.isEmpty || !customers.isEmpty {
            loadState = .loaded
            return
        }

        if !loadErrors.isEmpty, loadErrors.allSatisfy(isRouteNotDeployed(_:)) {
            loadState = .backendUnavailable
            error = nil
        } else if let firstError = loadErrors.first {
            self.error = localizedMessage(for: firstError, fallback: "Servisní připomínky se nepodařilo načíst.")
        }
    }

    func loadVehiclesForCustomer(customerId: Int, token: String) async {
        do {
            selectedCustomerVehicles = try await service.fetchCustomerVehicles(customerId: customerId, token: token)
        } catch is CancellationError {
            return
        } catch {
            self.error = localizedMessage(for: error, fallback: "Vozidla klienta se nepodařilo načíst.")
        }
    }

    func createReminder(_ request: ServiceWorkspaceReminderCreateRequest, token: String) async {
        do {
            _ = try await service.createReminder(request, token: token)
            await load(token: token)
        } catch is CancellationError {
            return
        } catch {
            self.error = localizedMessage(for: error, fallback: "Servisní připomínku se nepodařilo uložit.")
        }
    }

    func updateReminder(reminderId: Int, request: ServiceWorkspaceReminderUpdateRequest, token: String) async {
        do {
            _ = try await service.updateReminder(reminderId: reminderId, request: request, token: token)
            await load(token: token)
        } catch is CancellationError {
            return
        } catch {
            self.error = localizedMessage(for: error, fallback: "Servisní připomínku se nepodařilo upravit.")
        }
    }

    func deleteReminder(reminderId: Int, token: String) async {
        do {
            try await service.deleteReminder(reminderId: reminderId, token: token)
            await load(token: token)
        } catch is CancellationError {
            return
        } catch {
            self.error = localizedMessage(for: error, fallback: "Servisní připomínku se nepodařilo smazat.")
        }
    }

    private func localizedMessage(for error: Error, fallback: String) -> String {
        UserFacingErrorMapper.message(for: error, context: .account, fallback: fallback)
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
}
