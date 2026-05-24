import Foundation

struct UserProfile: Codable, Identifiable, Hashable {
    let id: Int
    let email: String
    var name: String?
    var ico: String?
    var dic: String?
    var street: String?
    var streetNumber: String?
    var city: String?
    var zip: String?
    var phone: String?
    var role: String
    var createdAt: Date?
    var accountStatus: String?
    var emailVerifiedAt: Date?
    var phoneE164: String?
    var phoneVerifiedAt: Date?
    var phoneVerificationStatus: String?
}

struct LoginRequest: Encodable {
    let email: String
    let password: String
    let expectedRole: String?
}

struct LoginResponse: Decodable {
    let accessToken: String?
    let tokenType: String
    let user: UserProfile?
    let twoFactorRequired: Bool
    let challengeToken: String?
    let challengeExpiresIn: Int?

    enum CodingKeys: String, CodingKey {
        case accessToken
        case token
        case tokenType
        case user
        case twoFactorRequired
        case challengeToken
        case challengeExpiresIn
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        accessToken = try container.decodeIfPresent(String.self, forKey: .accessToken)
            ?? container.decodeIfPresent(String.self, forKey: .token)
        tokenType = try container.decodeIfPresent(String.self, forKey: .tokenType) ?? "bearer"
        user = try container.decodeIfPresent(UserProfile.self, forKey: .user)
        twoFactorRequired = try container.decodeIfPresent(Bool.self, forKey: .twoFactorRequired) ?? false
        challengeToken = try container.decodeIfPresent(String.self, forKey: .challengeToken)
        challengeExpiresIn = try container.decodeIfPresent(Int.self, forKey: .challengeExpiresIn)
    }
}

struct TwoFactorVerifyRequest: Encodable {
    let challengeToken: String
    let code: String
}

struct TokenResponse: Decodable {
    let accessToken: String
    let tokenType: String
    let user: UserProfile?

    enum CodingKeys: String, CodingKey {
        case accessToken
        case token
        case tokenType
        case user
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        let token = try container.decodeIfPresent(String.self, forKey: .accessToken)
            ?? (try container.decodeIfPresent(String.self, forKey: .token))
        guard let token, !token.isEmpty else {
            throw DecodingError.dataCorruptedError(forKey: .accessToken, in: container, debugDescription: "Missing access token")
        }
        accessToken = token
        tokenType = try container.decodeIfPresent(String.self, forKey: .tokenType) ?? "bearer"
        user = try container.decodeIfPresent(UserProfile.self, forKey: .user)
    }
}

struct RegisterTokenResponse: Decodable {
    let accessToken: String?
    let tokenType: String?
    let user: UserProfile?
    let verificationRequired: Bool?
    let message: String?
    let emailSent: Bool?
    let registrationEmailStatus: String?
}

struct UserUpdateRequest: Encodable {
    var name: String?
    var phone: String?
    var city: String?
    var street: String?
    var streetNumber: String?
    var zip: String?
}

struct SecuritySettingsResponse: Decodable {
    let twoFactorEnabled: Bool
    let totpConfigured: Bool
    let biometricEnabled: Bool
    let biometricPreferred: Bool
}

struct TotpSetupResponse: Decodable {
    let secret: String
    let otpauthUri: String
    let digits: Int
    let periodSeconds: Int
    let message: String
}

struct TotpEnableRequest: Encodable {
    let code: String
}

struct TotpDisableRequest: Encodable {
    let currentPassword: String
    let code: String
}

struct BiometricSecurityPreferenceRequest: Encodable {
    let enabled: Bool
    let preferred: Bool?
}

struct SecurityActionResponse: Decodable {
    let message: String
    let twoFactorEnabled: Bool?
    let biometricEnabled: Bool?
    let biometricPreferred: Bool?
}
