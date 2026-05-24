import Foundation

enum APIError: Error, LocalizedError {
    case invalidURL
    case unauthorized
    case forbidden
    case developerAppRequired
    case serverError(String)
    case decodingError
    case transportError(String)

    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "Neplatná URL API."
        case .unauthorized:
            return "Relace vypršela. Přihlaste se znovu."
        case .forbidden:
            return "Nemáte oprávnění pro tuto akci."
        case .developerAppRequired:
            return "Developer/Admin účet se přihlašuje v samostatné developer aplikaci."
        case .serverError(let message):
            return message
        case .decodingError:
            return "Nepodařilo se zpracovat odpověď serveru."
        case .transportError(let message):
            return message
        }
    }
}

enum UserFacingErrorContext {
    case login
    case twoFactor
    case localProtection
    case account
    case vehicleDetailLoad
    case vehicleDetailSave
}

enum UserFacingErrorMapper {
    static func message(for error: Error, context: UserFacingErrorContext, fallback: String) -> String {
        switch error {
        case let apiError as APIError:
            switch apiError {
            case .invalidURL, .decodingError:
                return fallback
            case .unauthorized:
                switch context {
                case .login, .twoFactor:
                    return "Přihlášení se nepodařilo. Zkontrolujte zadané údaje a zkuste to znovu."
                default:
                    return "Relace vypršela. Přihlaste se znovu."
                }
            case .forbidden:
                return "Nemáte oprávnění pro tuto akci."
            case .developerAppRequired:
                return "Administrátorský nebo developer účet se v této aplikaci nepřihlašuje."
            case .serverError(let message), .transportError(let message):
                return normalize(raw: message, context: context, fallback: fallback)
            }
        default:
            return normalize(raw: error.localizedDescription, context: context, fallback: fallback)
        }
    }

    private static func normalize(raw: String, context: UserFacingErrorContext, fallback: String) -> String {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return fallback }

        let lowered = trimmed.lowercased()
        if lowered == "not found" || lowered.contains("404") {
            return fallback
        }
        if lowered.contains("timed out") || lowered.contains("čas vypršel") || lowered.contains("trvalo příliš dlouho") {
            return "Server odpovídá příliš dlouho. Zkuste to znovu."
        }
        if lowered.contains("offline")
            || lowered.contains("internet")
            || lowered.contains("network")
            || lowered.contains("spojení")
            || lowered.contains("could not connect")
            || lowered.contains("not connected")
        {
            return "Nepodařilo se připojit k serveru."
        }
        if context == .twoFactor && (lowered.contains("2fa") || lowered.contains("otp") || lowered.contains("totp")) {
            return "Ověření 2FA se nepodařilo. Zkontrolujte kód a zkuste to znovu."
        }
        if context == .account && lowered.contains("passkey/webauthn") {
            return "Preference byla uložena, ale plné biometrické přihlášení účtu backend zatím nepodporuje."
        }
        if looksTechnicalEnglish(lowered) {
            return fallback
        }
        return trimmed
    }

    private static func looksTechnicalEnglish(_ text: String) -> Bool {
        [
            "request",
            "response",
            "failed",
            "invalid",
            "unsupported",
            "exception",
            "decoding",
            "cloudflare",
            "server error",
            "connection",
        ].contains { text.contains($0) }
    }
}
