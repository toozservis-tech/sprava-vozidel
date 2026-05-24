import Foundation

@MainActor
final class ServiceViewModel: ObservableObject {
    enum ErrorContext {
        case remindersLoad
        case servicesLoad
        case reminderSave
        case reminderDelete
        case accessGrant
        case accessRequestApprove
        case accessRequestReject
        case accessRevoke
        case serviceDisconnect
        case reminderSettings
    }

    @Published var reminders: [Reminder] = []
    @Published var servicesDiscovery: [ServiceContact] = []
    @Published var myContacts: [ServiceContact] = []
    @Published var accessRequests: [ServiceAccessRequest] = []
    @Published var accessGrants: [VehicleAccessGrant] = []
    @Published var reminderSettings: ReminderSettings?
    @Published var isLoading = false
    @Published var error: String?
    @Published var remindersBackendUnavailable = false
    @Published var servicesBackendUnavailable = false

    private let api: APIClient
    private let featureService: UserFeatureService
    private var remindersLoadedAt: Date?
    private var servicesLoadedAt: Date?
    private let reloadTTL: TimeInterval = 45

    init(api: APIClient, featureService: UserFeatureService) {
        self.api = api
        self.featureService = featureService
    }

    func loadRemindersIfNeeded(token: String, force: Bool = false) async {
        if !force,
           let remindersLoadedAt,
           Date().timeIntervalSince(remindersLoadedAt) < reloadTTL,
           (!reminders.isEmpty || reminderSettings != nil) {
            return
        }
        await loadReminders(token: token)
    }

    func loadServicesIfNeeded(token: String, force: Bool = false) async {
        if !force,
           let servicesLoadedAt,
           Date().timeIntervalSince(servicesLoadedAt) < reloadTTL,
           (!servicesDiscovery.isEmpty || !myContacts.isEmpty || !accessRequests.isEmpty || !accessGrants.isEmpty) {
            return
        }
        await loadServices(token: token)
    }

    func load(token: String) async {
        isLoading = true
        error = nil
        defer { isLoading = false }

        async let remindersReq: [Reminder] = api.request(.get("/api/v1/reminders"), token: token)
        async let discoveryReq = featureService.fetchServiceDiscovery(token: token)
        async let contactsReq = featureService.fetchMyServiceContacts(token: token)
        async let requestsReq = featureService.fetchServiceAccessRequests(token: token)
        async let grantsReq = featureService.fetchVehicleAccessGrants(token: token)
        async let settingsReq = featureService.fetchReminderSettings(token: token)

        var loadErrors: [String] = []

        do {
            self.reminders = try await remindersReq
        } catch {
            self.reminders = []
            loadErrors.append(userFacingMessage(for: error, context: .remindersLoad))
        }

        do {
            self.servicesDiscovery = sortServiceDiscovery(try await discoveryReq.services)
        } catch {
            self.servicesDiscovery = []
            loadErrors.append(userFacingMessage(for: error, context: .servicesLoad))
        }

        do {
            self.myContacts = try await contactsReq.services
        } catch {
            self.myContacts = []
            loadErrors.append(userFacingMessage(for: error, context: .servicesLoad))
        }

        do {
            self.accessRequests = try await requestsReq.requests
        } catch {
            self.accessRequests = []
            loadErrors.append(userFacingMessage(for: error, context: .servicesLoad))
        }

        do {
            self.accessGrants = try await grantsReq.grants
        } catch {
            self.accessGrants = []
            loadErrors.append(userFacingMessage(for: error, context: .servicesLoad))
        }

        do {
            self.reminderSettings = try await settingsReq
        } catch {
            self.reminderSettings = nil
            loadErrors.append(userFacingMessage(for: error, context: .reminderSettings))
        }

        let hasAnyData =
            !reminders.isEmpty ||
            !servicesDiscovery.isEmpty ||
            !myContacts.isEmpty ||
            !accessRequests.isEmpty ||
            !accessGrants.isEmpty

        if !hasAnyData, let first = loadErrors.first {
            self.error = first
        } else {
            self.error = nil
        }
    }

    func loadReminders(token: String) async {
        isLoading = true
        error = nil
        remindersBackendUnavailable = false
        defer { isLoading = false }

        async let remindersReq: [Reminder] = api.request(.get("/api/v1/reminders"), token: token)
        async let settingsReq = featureService.fetchReminderSettings(token: token)

        var remindersError: Error?
        var settingsError: Error?

        do {
            self.reminders = try await remindersReq
        } catch {
            self.reminders = []
            remindersError = error
        }

        do {
            self.reminderSettings = try await settingsReq
        } catch {
            self.reminderSettings = nil
            settingsError = error
        }

        if remindersError == nil || settingsError == nil {
            self.remindersLoadedAt = Date()
        }

        let onlyNotDeployedErrors = [remindersError, settingsError]
            .compactMap { $0 }
            .allSatisfy(isRouteNotDeployed(_:))

        if reminders.isEmpty, reminderSettings == nil, onlyNotDeployedErrors, remindersError != nil, settingsError != nil {
            remindersBackendUnavailable = true
            self.error = nil
        } else if let remindersError {
            self.error = userFacingMessage(for: remindersError, context: .remindersLoad)
        } else if let settingsError {
            self.error = userFacingMessage(for: settingsError, context: .reminderSettings)
        }
    }

    func loadServices(token: String) async {
        isLoading = true
        error = nil
        servicesBackendUnavailable = false
        defer { isLoading = false }

        async let discoveryReq = featureService.fetchServiceDiscovery(token: token)
        async let contactsReq = featureService.fetchMyServiceContacts(token: token)
        async let requestsReq = featureService.fetchServiceAccessRequests(token: token)
        async let grantsReq = featureService.fetchVehicleAccessGrants(token: token)

        var loadErrors: [Error] = []

        do {
            self.servicesDiscovery = sortServiceDiscovery(try await discoveryReq.services)
        } catch {
            self.servicesDiscovery = []
            loadErrors.append(error)
        }
        do {
            self.myContacts = try await contactsReq.services
        } catch {
            self.myContacts = []
            loadErrors.append(error)
        }
        do {
            self.accessRequests = try await requestsReq.requests
        } catch {
            self.accessRequests = []
            loadErrors.append(error)
        }
        do {
            self.accessGrants = try await grantsReq.grants
        } catch {
            self.accessGrants = []
            loadErrors.append(error)
        }

        if loadErrors.count < 4 {
            self.servicesLoadedAt = Date()
        }

        let hasAnyData =
            !servicesDiscovery.isEmpty ||
            !myContacts.isEmpty ||
            !accessRequests.isEmpty ||
            !accessGrants.isEmpty

        let onlyNotDeployedErrors = !loadErrors.isEmpty && loadErrors.allSatisfy(isRouteNotDeployed(_:))
        if !hasAnyData, onlyNotDeployedErrors {
            servicesBackendUnavailable = true
            self.error = nil
        } else if let firstError = loadErrors.first, !hasAnyData {
            self.error = userFacingMessage(for: firstError, context: .servicesLoad)
        }
    }

    func createReminder(_ request: ReminderCreateRequest, token: String) async {
        do {
            _ = try await featureService.createReminder(request, token: token)
            await loadRemindersIfNeeded(token: token, force: true)
        } catch {
            self.error = userFacingMessage(for: error, context: .reminderSave)
        }
    }

    func updateReminder(id: Int, _ request: ReminderUpdateRequest, token: String) async {
        do {
            _ = try await featureService.updateReminder(id: id, request, token: token)
            await loadRemindersIfNeeded(token: token, force: true)
        } catch {
            self.error = userFacingMessage(for: error, context: .reminderSave)
        }
    }

    func deleteReminder(id: Int, token: String) async {
        do {
            try await featureService.deleteReminder(id: id, token: token)
            await loadRemindersIfNeeded(token: token, force: true)
        } catch {
            self.error = userFacingMessage(for: error, context: .reminderDelete)
        }
    }

    func updateReminderSettings(notificationMethod: String, daysBefore: Int, token: String) async {
        do {
            _ = try await featureService.updateReminderSettings(
                ReminderSettingsUpdateRequest(
                    enabled: reminderSettings?.enabled ?? true,
                    notification: ReminderNotificationSettingsUpdateRequest(
                        notificationMethod: notificationMethod,
                        notifyDaysBefore: daysBefore
                    )
                ),
                token: token
            )
            await loadRemindersIfNeeded(token: token, force: true)
        } catch {
            self.error = userFacingMessage(for: error, context: .reminderSettings)
        }
    }

    func grantVehicleAccess(vehicleId: Int, serviceId: Int, token: String) async {
        do {
            try await featureService.grantVehicleAccess(
                VehicleAccessGrantRequest(vehicleId: vehicleId, serviceId: serviceId, note: nil, conflictStrategy: "keep"),
                token: token
            )
            await loadServicesIfNeeded(token: token, force: true)
        } catch {
            self.error = userFacingMessage(for: error, context: .accessGrant)
        }
    }

    func revokeVehicleAccess(serviceId: Int, vehicleId: Int, token: String) async {
        do {
            try await featureService.revokeVehicleAccess(serviceId: serviceId, vehicleId: vehicleId, token: token)
            await loadServicesIfNeeded(token: token, force: true)
        } catch {
            self.error = userFacingMessage(for: error, context: .accessRevoke)
        }
    }

    func approveAccessRequest(requestId: Int, token: String) async {
        do {
            try await featureService.resolveServiceAccessRequest(
                requestId: requestId,
                decision: "approved",
                note: nil,
                token: token
            )
            await loadServicesIfNeeded(token: token, force: true)
        } catch {
            self.error = userFacingMessage(for: error, context: .accessRequestApprove)
        }
    }

    func rejectAccessRequest(requestId: Int, token: String) async {
        do {
            try await featureService.resolveServiceAccessRequest(
                requestId: requestId,
                decision: "rejected",
                note: nil,
                token: token
            )
            await loadServicesIfNeeded(token: token, force: true)
        } catch {
            self.error = userFacingMessage(for: error, context: .accessRequestReject)
        }
    }

    func disconnectService(serviceId: Int, token: String) async {
        do {
            try await featureService.disconnectService(serviceId: serviceId, token: token)
            await loadServicesIfNeeded(token: token, force: true)
        } catch {
            self.error = userFacingMessage(for: error, context: .serviceDisconnect)
        }
    }

    private func userFacingMessage(for error: Error, context: ErrorContext) -> String {
#if DEBUG
        print("[ServiceViewModel] \(context) failed: \(error.localizedDescription)")
#endif
        let raw = error.localizedDescription.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if raw.contains("unable to parse string as an integer") || raw.contains("input should be a valid integer") {
            switch context {
            case .remindersLoad, .reminderSave, .reminderDelete, .reminderSettings:
                return "Nepodařilo se načíst připomínky. Zkuste to prosím znovu."
            default:
                return "Nepodařilo se načíst servisní data. Zkuste to prosím znovu."
            }
        }

        switch context {
        case .remindersLoad:
            return UserFacingErrorMapper.message(for: error, context: .account, fallback: "Nepodařilo se načíst připomínky. Zkuste to prosím znovu.")
        case .servicesLoad:
            return UserFacingErrorMapper.message(for: error, context: .account, fallback: "Nepodařilo se načíst servisní kontakty a přístupy. Zkuste to prosím znovu.")
        case .reminderSave:
            return UserFacingErrorMapper.message(for: error, context: .account, fallback: "Připomínku se nepodařilo uložit. Zkontrolujte zadané údaje a zkuste to znovu.")
        case .reminderDelete:
            return UserFacingErrorMapper.message(for: error, context: .account, fallback: "Připomínku se nepodařilo smazat. Zkuste to prosím znovu.")
        case .accessGrant:
            return UserFacingErrorMapper.message(for: error, context: .account, fallback: "Přístup k vozidlu se nepodařilo udělit. Zkontrolujte výběr vozidla a zkuste to znovu.")
        case .accessRequestApprove:
            return UserFacingErrorMapper.message(for: error, context: .account, fallback: "Žádost o přístup se nepodařilo schválit.")
        case .accessRequestReject:
            return UserFacingErrorMapper.message(for: error, context: .account, fallback: "Žádost o přístup se nepodařilo zamítnout.")
        case .accessRevoke:
            return UserFacingErrorMapper.message(for: error, context: .account, fallback: "Přístup se nepodařilo odebrat. Zkuste to prosím znovu.")
        case .serviceDisconnect:
            return UserFacingErrorMapper.message(for: error, context: .account, fallback: "Servisní kontakt se nepodařilo odpojit. Zkuste to prosím znovu.")
        case .reminderSettings:
            return UserFacingErrorMapper.message(for: error, context: .account, fallback: "Nastavení připomínek se nepodařilo uložit. Zkuste to prosím znovu.")
        }
    }

    private func sortServiceDiscovery(_ services: [ServiceContact]) -> [ServiceContact] {
        services.sorted { lhs, rhs in
            let lhsDistance = lhs.distanceKm ?? .greatestFiniteMagnitude
            let rhsDistance = rhs.distanceKm ?? .greatestFiniteMagnitude
            if lhsDistance != rhsDistance {
                return lhsDistance < rhsDistance
            }
            return lhs.name.localizedCaseInsensitiveCompare(rhs.name) == .orderedAscending
        }
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
