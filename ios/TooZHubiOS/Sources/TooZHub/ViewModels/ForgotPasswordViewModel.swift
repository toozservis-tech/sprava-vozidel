import Foundation

@MainActor
final class ForgotPasswordViewModel: ObservableObject {
    @Published var email = ""
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var infoMessage: String?
    @Published var resetURL: String?

    func submit(auth: AuthManager) async {
        errorMessage = nil
        infoMessage = nil
        resetURL = nil

        let normalizedEmail = email.trimmingCharacters(in: .whitespacesAndNewlines)
        guard normalizedEmail.contains("@"), normalizedEmail.contains(".") else {
            errorMessage = "Zadejte platný e-mail."
            return
        }

        isLoading = true
        defer { isLoading = false }

        do {
            let response = try await auth.requestPasswordReset(email: normalizedEmail)
            if response.emailSent == true {
                infoMessage = response.message ?? "Reset odkaz byl odeslán na e-mail."
            } else if let reset = response.resetUrl, !reset.isEmpty {
                infoMessage = response.message ?? "SMTP není aktivní, použijte testovací odkaz."
                resetURL = reset
            } else {
                infoMessage = response.message ?? "Požadavek byl přijat."
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
