import Foundation

final class ServiceWorkspaceService {
    enum BackendMode: Equatable {
        case serviceAccessModel
        case legacyWorkspace
        case unavailable
    }

    private let api: APIClient

    init(api: APIClient) {
        self.api = api
    }

    func detectBackendMode(token: String) async throws -> BackendMode {
        do {
            _ = try await api.requestData(.get("/api/v1/services/workspace/approved-vehicles"), token: token)
            return .serviceAccessModel
        } catch let apiError as APIError {
            switch apiError {
            case .unauthorized, .forbidden:
                throw apiError
            case .serverError(let message), .transportError(let message):
                if isNotFound(message) {
                    do {
                        _ = try await api.requestData(.get("/api/v1/services/workspace/customers"), token: token)
                        return .legacyWorkspace
                    } catch let fallbackError as APIError {
                        switch fallbackError {
                        case .unauthorized, .forbidden:
                            throw fallbackError
                        default:
                            return .unavailable
                        }
                    } catch {
                        return .unavailable
                    }
                }
                return .unavailable
            default:
                return .unavailable
            }
        } catch {
            return .unavailable
        }
    }

    func fetchCustomers(token: String) async throws -> [ServiceWorkspaceCustomer] {
        try await api.request(.get("/api/v1/services/workspace/customers"), token: token)
    }

    func fetchCustomerVehicles(customerId: Int, token: String) async throws -> [ServiceWorkspaceVehicle] {
        try await api.request(.get("/api/v1/services/workspace/customers/\(customerId)/vehicles"), token: token)
    }

    func createCustomerVehicle(customerId: Int, request: ServiceWorkspaceVehicleCreateRequest, token: String) async throws {
        let body = try api.encodeBody(request)
        try await api.requestNoContent(.post("/api/v1/services/workspace/customers/\(customerId)/vehicles", body: body), token: token)
    }

    func createPendingVehicleRegistration(
        _ request: PendingVehicleRegistrationRequest,
        token: String
    ) async throws -> PendingVehicleRegistrationResponse {
        let body = try api.encodeBody(request)
        return try await api.request(.post("/api/v1/services/workspace/pending-vehicles", body: body), token: token)
    }

    func fetchReminders(token: String) async throws -> [ServiceWorkspaceReminder] {
        try await api.request(
            .get(
                "/api/v1/services/workspace/reminders",
                queryItems: [
                    URLQueryItem(name: "include_completed", value: "true"),
                    URLQueryItem(name: "limit", value: "200")
                ]
            ),
            token: token
        )
    }

    func lookupVehicle(query: String, token: String) async throws -> ServiceVehicleLookupResponse {
        let normalized = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !normalized.isEmpty else {
            return ServiceVehicleLookupResponse(candidates: [])
        }
        let body = try api.encodeBody(ServiceVehicleLookupRequest(query: normalized))
        return try await api.request(.post("/api/v1/services/workspace/vehicle-lookup", body: body), token: token)
    }

    func createAccessRequest(_ request: ServiceAccessRequestCreateRequest, token: String) async throws -> ServiceAccessRequestCreateResponse {
        let body = try api.encodeBody(request)
        return try await api.request(.post("/api/v1/services/workspace/access-requests", body: body), token: token)
    }

    func fetchApprovedVehicles(token: String) async throws -> ServiceApprovedVehicleListResponse {
        try await api.request(.get("/api/v1/services/workspace/approved-vehicles"), token: token)
    }

    func createReminder(_ request: ServiceWorkspaceReminderCreateRequest, token: String) async throws -> ServiceWorkspaceReminder {
        let body = try api.encodeBody(request)
        return try await api.request(.post("/api/v1/services/workspace/reminders", body: body), token: token)
    }

    func updateReminder(reminderId: Int, request: ServiceWorkspaceReminderUpdateRequest, token: String) async throws -> ServiceWorkspaceReminder {
        let body = try api.encodeBody(request)
        return try await api.request(.put("/api/v1/services/workspace/reminders/\(reminderId)", body: body), token: token)
    }

    func deleteReminder(reminderId: Int, token: String) async throws {
        try await api.requestNoContent(.delete("/api/v1/services/workspace/reminders/\(reminderId)"), token: token)
    }

    private func isNotFound(_ message: String) -> Bool {
        let lowered = message.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return lowered == "not found" || lowered.contains("404")
    }
}
