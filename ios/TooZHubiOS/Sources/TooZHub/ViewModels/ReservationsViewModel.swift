import Foundation

@MainActor
final class ReservationsViewModel: ObservableObject {
    enum ErrorContext {
        case load
        case create
        case update
        case delete
    }

    @Published var reservations: [Reservation] = []
    @Published var services: [ServiceContact] = []
    @Published var vehicleOptions: [ReservationVehicleOption] = []
    @Published var isLoading = false
    @Published var error: String?

    private let service: ReservationService
    private let featureService: UserFeatureService
    private var hasLoadedOnce = false
    private var lastLoadedAt: Date?
    private var lastLoadedRole: String?
    private let reloadTTL: TimeInterval = 45

    init(service: ReservationService, featureService: UserFeatureService) {
        self.service = service
        self.featureService = featureService
    }

    func loadIfNeeded(token: String, role: String, force: Bool = false) async {
        let normalizedRole = role.lowercased()
        if !force,
           hasLoadedOnce,
           lastLoadedRole == normalizedRole,
           let lastLoadedAt,
           Date().timeIntervalSince(lastLoadedAt) < reloadTTL {
            return
        }
        await load(token: token, role: role)
    }

    func load(token: String, role: String) async {
        isLoading = true
        error = nil
        defer { isLoading = false }

        do {
            let normalizedRole = role.lowercased()
            async let reservations: [Reservation] = (normalizedRole == "service")
                ? service.fetchServiceReservations(token: token)
                : service.fetchReservations(token: token)
            async let discovery = service.fetchServiceDiscovery(token: token)
            async let linkedContacts = service.fetchMyServiceContacts(token: token)
            async let vehicles = service.fetchReservationVehicleOptions(token: token)
            self.reservations = try await reservations
            self.vehicleOptions = try await vehicles

            let discoveryServices = try await discovery
            let linked = try await linkedContacts
            var mergedServices = Dictionary(uniqueKeysWithValues: discoveryServices.map { ($0.id, $0) })
            for item in linked {
                mergedServices[item.id] = mergedServices[item.id] ?? item
            }
            self.services = mergedServices.values.sorted { lhs, rhs in
                lhs.name.localizedCaseInsensitiveCompare(rhs.name) == .orderedAscending
            }
            hasLoadedOnce = true
            lastLoadedAt = Date()
            lastLoadedRole = normalizedRole
        } catch is CancellationError {
            return
        } catch {
            self.error = userFacingMessage(for: error, context: .load)
        }
    }

    func createReservation(
        vehicleId: Int,
        serviceId: Int,
        type: String,
        note: String,
        start: Date,
        token: String,
        role: String
    ) async {
        do {
            _ = try await service.createReservation(
                ReservationCreateRequest(
                    serviceId: serviceId,
                    vehicleId: vehicleId,
                    serviceType: type,
                    note: note.isEmpty ? nil : note,
                    startDatetime: start,
                    endDatetime: nil,
                    createdVia: "ios_app"
                ),
                token: token
            )
            await loadIfNeeded(token: token, role: role, force: true)
        } catch is CancellationError {
            return
        } catch {
            self.error = userFacingMessage(for: error, context: .create)
        }
    }

    func cancelReservation(reservationId: Int, token: String, role: String) async {
        await updateReservationStatus(reservationId: reservationId, status: "CANCELLED", token: token, role: role)
    }

    func confirmReservation(reservationId: Int, token: String, role: String) async {
        await updateReservationStatus(reservationId: reservationId, status: "CONFIRMED", token: token, role: role)
    }

    func completeReservation(reservationId: Int, token: String, role: String) async {
        await updateReservationStatus(reservationId: reservationId, status: "COMPLETED", token: token, role: role)
    }

    func deleteReservation(reservationId: Int, token: String, role: String) async {
        do {
            try await featureService.deleteReservation(reservationId: reservationId, token: token)
            await loadIfNeeded(token: token, role: role, force: true)
        } catch is CancellationError {
            return
        } catch {
            self.error = userFacingMessage(for: error, context: .delete)
        }
    }

    private func updateReservationStatus(reservationId: Int, status: String, token: String, role: String) async {
        do {
            _ = try await featureService.updateReservationStatus(reservationId: reservationId, status: status, token: token)
            await loadIfNeeded(token: token, role: role, force: true)
        } catch is CancellationError {
            return
        } catch {
            self.error = userFacingMessage(for: error, context: .update)
        }
    }

    private func userFacingMessage(for error: Error, context: ErrorContext) -> String {
        switch context {
        case .load:
            return UserFacingErrorMapper.message(
                for: error,
                context: .account,
                fallback: "Rezervace se nepodařilo načíst. Zkuste to prosím znovu."
            )
        case .create:
            return UserFacingErrorMapper.message(
                for: error,
                context: .account,
                fallback: "Rezervaci se nepodařilo vytvořit. Zkontrolujte termín a zkuste to znovu."
            )
        case .update:
            return UserFacingErrorMapper.message(
                for: error,
                context: .account,
                fallback: "Změnu rezervace se nepodařilo uložit. Zkuste to prosím znovu."
            )
        case .delete:
            return UserFacingErrorMapper.message(
                for: error,
                context: .account,
                fallback: "Rezervaci se nepodařilo smazat. Zkuste to prosím znovu."
            )
        }
    }
}
