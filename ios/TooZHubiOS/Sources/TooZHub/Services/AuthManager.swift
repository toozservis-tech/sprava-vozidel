import Foundation

@MainActor
final class AuthManager: ObservableObject {
    @Published private(set) var token: String?
    @Published private(set) var user: UserProfile?
    @Published var isLoading = false
    @Published private(set) var privilegedLoginEnabled = false

    private let api: APIClient
    private let storage: SecureTokenStorage
    private let featureService: AuthFeatureService

    init(api: APIClient, storage: SecureTokenStorage = SecureTokenStorage()) {
        self.api = api
        self.storage = storage
        self.featureService = AuthFeatureService(api: api)
        self.token = storage.loadToken()
    }

    var isAuthenticated: Bool {
        token != nil
    }

    func setPrivilegedLoginEnabled(_ enabled: Bool) {
#if DEBUG
        privilegedLoginEnabled = enabled
#else
        privilegedLoginEnabled = false
#endif
    }

    func bootstrap() async {
        guard let token else { return }
        isLoading = true
        defer { isLoading = false }

        do {
            let user: UserProfile = try await api.request(.get("/user/me"), token: token)
            self.user = user
        } catch {
            logout()
        }
    }

    func login(email: String, password: String, expectedRole: String = "user") async throws -> LoginResponse {
        let request = LoginRequest(email: email, password: password, expectedRole: expectedRole)
        let body = try api.encodeBody(request)
        let response: LoginResponse = try await api.request(.post("/user/login", body: body), token: nil)

        if let token = response.accessToken {
            if let user = response.user {
                let role = (user.role).lowercased()
                if shouldBlockPrivileged(role) {
                    throw APIError.developerAppRequired
                }
                storage.saveToken(token)
                self.token = token
                self.user = user
            } else {
                let profile: UserProfile = try await api.request(.get("/user/me"), token: token)
                let role = profile.role.lowercased()
                if shouldBlockPrivileged(role) {
                    throw APIError.developerAppRequired
                }
                storage.saveToken(token)
                self.token = token
                self.user = profile
            }
        } else if !response.twoFactorRequired {
            throw APIError.serverError("Server nevrátil přístupový token.")
        }

        return response
    }

    func verify2FA(challengeToken: String, code: String) async throws {
        let request = TwoFactorVerifyRequest(challengeToken: challengeToken, code: code)
        let body = try api.encodeBody(request)
        let response: TokenResponse = try await api.request(.post("/user/login/2fa", body: body), token: nil)
        let resolvedUser: UserProfile
        if let user = response.user {
            resolvedUser = user
        } else {
            resolvedUser = try await api.request(.get("/user/me"), token: response.accessToken)
        }
        let role = resolvedUser.role.lowercased()
        if shouldBlockPrivileged(role) {
            throw APIError.developerAppRequired
        }
        storage.saveToken(response.accessToken)
        token = response.accessToken
        user = resolvedUser
    }

    func registerUser(_ request: UserRegisterRequest) async throws -> RegisterTokenResponse {
        let response = try await featureService.registerUser(request)
        if let token = response.accessToken, !token.isEmpty, let user = response.user {
            completeAuthentication(token: token, user: user)
        } else {
            logout()
        }
        return response
    }

    func requestServiceRegistration(_ request: ServiceRegistrationRequest) async throws -> ServiceRegistrationResponse {
        try await featureService.registerServiceRequest(request)
    }

    func requestPasswordReset(email: String) async throws -> ForgotPasswordResponse {
        try await featureService.requestPasswordReset(email: email)
    }

    func lookupAresPublic(ico: String) async throws -> AresPublicResponse {
        try await featureService.lookupAresPublic(ico: ico)
    }

    func refreshProfile() async {
        guard let token else { return }
        do {
            let profile: UserProfile = try await api.request(.get("/user/me"), token: token)
            user = profile
        } catch {
            if case APIError.unauthorized = error {
                logout()
            }
        }
    }

    func logout() {
        storage.clearToken()
        token = nil
        user = nil
    }

    private func completeAuthentication(token: String, user: UserProfile) {
        let role = user.role.lowercased()
        if shouldBlockPrivileged(role) {
            return
        }
        storage.saveToken(token)
        self.token = token
        self.user = user
    }

    private func shouldBlockPrivileged(_ role: String) -> Bool {
#if DEBUG
        (role == "developer_admin" || role == "admin") && !privilegedLoginEnabled
#else
        role == "developer_admin" || role == "admin"
#endif
    }
}
