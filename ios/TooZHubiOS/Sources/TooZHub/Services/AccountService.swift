import Foundation

final class AccountService {
    private let api: APIClient

    init(api: APIClient) {
        self.api = api
    }

    func fetchProfile(token: String) async throws -> UserProfile {
        try await api.request(.get("/user/me"), token: token)
    }

    func updateProfile(_ request: UserUpdateRequest, token: String) async throws -> UserProfile {
        let body = try api.encodeBody(request)
        return try await api.request(.put("/user/me", body: body), token: token)
    }

    func fetchSecuritySettings(token: String) async throws -> SecuritySettingsResponse {
        try await api.request(.get("/user/security/settings"), token: token)
    }

    func setupTotp(token: String) async throws -> TotpSetupResponse {
        try await api.request(.post("/user/security/totp/setup", body: nil), token: token)
    }

    func enableTotp(code: String, token: String) async throws -> SecurityActionResponse {
        let body = try api.encodeBody(TotpEnableRequest(code: code))
        return try await api.request(.post("/user/security/totp/enable", body: body), token: token)
    }

    func disableTotp(currentPassword: String, code: String, token: String) async throws -> SecurityActionResponse {
        let body = try api.encodeBody(TotpDisableRequest(currentPassword: currentPassword, code: code))
        return try await api.request(.post("/user/security/totp/disable", body: body), token: token)
    }

    func updateBiometricPreference(enabled: Bool, preferred: Bool?, token: String) async throws -> SecurityActionResponse {
        let body = try api.encodeBody(BiometricSecurityPreferenceRequest(enabled: enabled, preferred: preferred))
        return try await api.request(.post("/user/security/biometric", body: body), token: token)
    }

    func fetchLicense(token: String) async throws -> LicenseStatus {
        try await api.request(.get("/api/v1/license/status"), token: token)
    }
}
