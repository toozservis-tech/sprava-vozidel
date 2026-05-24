import Foundation

@MainActor
final class LoginViewModel: ObservableObject {
    @Published var email = ""
    @Published var password = ""
    @Published var expectedRole = "user"
    @Published var twoFactorCode = ""
    @Published var challengeToken: String?
    @Published var isLoading = false
    @Published var errorMessage: String?

    func signIn(auth: AuthManager) async {
        errorMessage = nil
        let normalizedEmail = email.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let normalizedPassword = password.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !normalizedEmail.isEmpty, !normalizedPassword.isEmpty else {
            errorMessage = "Vyplňte e-mail a heslo."
            return
        }
        isLoading = true
        defer { isLoading = false }

        do {
            email = normalizedEmail
            let response = try await auth.login(email: normalizedEmail, password: normalizedPassword, expectedRole: expectedRole)
            if response.twoFactorRequired {
                errorMessage = "Účet vyžaduje 2FA. Doplňte kód."
                challengeToken = response.challengeToken
            } else {
                challengeToken = nil
            }
        } catch {
            errorMessage = UserFacingErrorMapper.message(
                for: error,
                context: .login,
                fallback: "Přihlášení se nepodařilo. Zkontrolujte e-mail, heslo a zkuste to znovu."
            )
        }
    }

    func verify2FA(auth: AuthManager) async {
        guard let challengeToken, !challengeToken.isEmpty else { return }
        let code = twoFactorCode.trimmingCharacters(in: .whitespacesAndNewlines)
        guard code.count >= 6 else {
            errorMessage = "Zadejte platný 2FA kód."
            return
        }
        isLoading = true
        defer { isLoading = false }

        do {
            try await auth.verify2FA(challengeToken: challengeToken, code: code)
            self.challengeToken = nil
            self.twoFactorCode = ""
            self.errorMessage = nil
        } catch {
            errorMessage = UserFacingErrorMapper.message(
                for: error,
                context: .twoFactor,
                fallback: "Ověření 2FA se nepodařilo. Zkontrolujte kód a zkuste to znovu."
            )
        }
    }
}
