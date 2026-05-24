import Foundation

@MainActor
final class DashboardViewModel: ObservableObject {
    @Published var isLoading = false
    @Published var error: String?
    @Published var vehicles: [Vehicle] = []
    @Published var reminders: [Reminder] = []
    @Published var analytics: AnalyticsSummary?
    @Published var monthlyCosts: [MonthlyCostEntry] = []
    @Published var notifications: [SystemNotification] = []

    private let service: DashboardService
    private var hasLoadedOnce = false
    private var lastLoadedAt: Date?
    private let reloadTTL: TimeInterval = 60

    init(service: DashboardService) {
        self.service = service
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
            let corePayload = try await service.loadDashboardCore(token: token)
            vehicles = corePayload.vehicles
            reminders = corePayload.reminders
            analytics = corePayload.analytics
            hasLoadedOnce = true
            lastLoadedAt = Date()
            Task { [weak self] in
                guard let self else { return }
                do {
                    let secondaryPayload = try await self.service.loadDashboardSecondary(token: token)
                    await MainActor.run {
                        self.monthlyCosts = secondaryPayload.monthlyCosts.entries
                        self.notifications = secondaryPayload.notifications
                    }
                } catch {
                }
            }
        } catch {
            self.error = error.localizedDescription
        }
    }
}
