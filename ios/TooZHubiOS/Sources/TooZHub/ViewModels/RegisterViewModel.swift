import Foundation

@MainActor
final class RegisterViewModel: ObservableObject {
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var infoMessage: String?

    @Published var email = ""
    @Published var password = ""
    @Published var passwordConfirm = ""
    @Published var name = ""
    @Published var ico = ""
    @Published var dic = ""
    @Published var street = ""
    @Published var streetNumber = ""
    @Published var city = ""
    @Published var zip = ""
    @Published var phone = ""

    func lookupAres(auth: AuthManager) async {
        let digits = ico.filter(\.isNumber)
        guard digits.count == 8 else {
            errorMessage = "IČO musí obsahovat přesně 8 číslic."
            return
        }
        isLoading = true
        errorMessage = nil
        infoMessage = nil
        defer { isLoading = false }

        do {
            let data = try await auth.lookupAresPublic(ico: digits)
            name = data.resolvedCompanyName ?? name
            dic = data.dic ?? dic
            street = data.resolvedStreet ?? street
            streetNumber = data.resolvedStreetNumber ?? streetNumber
            city = data.resolvedCity ?? city
            zip = data.resolvedZip ?? zip
            infoMessage = "Údaje z ARES byly načteny."
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func registerUser(auth: AuthManager) async -> Bool {
        errorMessage = nil
        infoMessage = nil

        let normalizedEmail = email.trimmingCharacters(in: .whitespacesAndNewlines)
        if !normalizedEmail.contains("@") || !normalizedEmail.contains(".") {
            errorMessage = "Zadejte platný e-mail."
            return false
        }
        if password.count < 6 {
            errorMessage = "Heslo musí mít alespoň 6 znaků."
            return false
        }
        if password != passwordConfirm {
            errorMessage = "Hesla se neshodují."
            return false
        }

        isLoading = true
        defer { isLoading = false }

        do {
            let response = try await auth.registerUser(
                UserRegisterRequest(
                    email: normalizedEmail,
                    password: password,
                    name: normalized(name),
                    ico: normalized(ico.filter(\.isNumber)),
                    dic: normalized(dic),
                    street: normalized(street),
                    streetNumber: normalized(streetNumber),
                    city: normalized(city),
                    zip: normalized(zip),
                    phone: normalized(phone)
                )
            )

            if response.registrationEmailStatus == "failed" {
                infoMessage = "Registrace proběhla, ale potvrzovací e-mail se nepodařilo odeslat."
            } else if response.verificationRequired == true {
                infoMessage = response.message ?? "Na e-mail jsme poslali ověřovací odkaz. Dokud e-mail neověříte, přihlášení nebude možné."
            }
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }

    private func normalized(_ value: String) -> String? {
        let cleaned = value.trimmingCharacters(in: .whitespacesAndNewlines)
        return cleaned.isEmpty ? nil : cleaned
    }
}
