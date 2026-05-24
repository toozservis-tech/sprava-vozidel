import Foundation

struct DashboardPayload {
    let vehicles: [Vehicle]
    let reminders: [Reminder]
    let analytics: AnalyticsSummary
    let monthlyCosts: MonthlyCosts
    let notifications: [SystemNotification]
}

struct DashboardCorePayload {
    let vehicles: [Vehicle]
    let reminders: [Reminder]
    let analytics: AnalyticsSummary
}

struct DashboardSecondaryPayload {
    let monthlyCosts: MonthlyCosts
    let notifications: [SystemNotification]
}

final class DashboardService {
    private let api: APIClient

    init(api: APIClient) {
        self.api = api
    }

    func loadDashboardCore(token: String) async throws -> DashboardCorePayload {
        async let vehicles: [Vehicle] = api.request(.get("/api/v1/vehicles"), token: token)
        async let reminders: [Reminder] = api.request(.get("/api/v1/reminders"), token: token)
        async let summary: AnalyticsSummary = api.request(.get("/api/v1/analytics/summary"), token: token)

        let v = try await vehicles
        let r = try await reminders
        let s = try await summary

        return DashboardCorePayload(
            vehicles: v,
            reminders: r,
            analytics: s
        )
    }

    func loadDashboardSecondary(token: String) async throws -> DashboardSecondaryPayload {
        async let monthly: MonthlyCosts = api.request(.get("/api/v1/analytics/monthly-costs", queryItems: [URLQueryItem(name: "months", value: "6")]), token: token)
        async let notificationsPayload: SystemNotificationsResponse = api.request(
            .get("/api/v1/system-notifications", queryItems: [URLQueryItem(name: "limit", value: "20")]),
            token: token
        )

        let monthlyValue = try await monthly
        let notificationsResponse = try await notificationsPayload
        let notifications = notificationsResponse.items

        return DashboardSecondaryPayload(
            monthlyCosts: monthlyValue,
            notifications: notifications
        )
    }

    func loadDashboard(token: String) async throws -> DashboardPayload {
        async let core = loadDashboardCore(token: token)
        async let secondary = loadDashboardSecondary(token: token)

        let corePayload = try await core
        let secondaryPayload = try await secondary

        return DashboardPayload(
            vehicles: corePayload.vehicles,
            reminders: corePayload.reminders,
            analytics: corePayload.analytics,
            monthlyCosts: secondaryPayload.monthlyCosts,
            notifications: secondaryPayload.notifications
        )
    }
}

