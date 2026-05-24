import Foundation

@MainActor
final class ServiceRegistrationViewModel: ObservableObject {
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var infoMessage: String?

    @Published var email = ""
    @Published var password = ""
    @Published var passwordConfirm = ""
    @Published var ico = ""
    @Published var serviceName = ""
    @Published var responsiblePerson = ""
    @Published var phone = ""
    @Published var street = ""
    @Published var streetNumber = ""
    @Published var city = ""
    @Published var zip = ""
    @Published var dic = ""
    @Published var registrationPurpose = ""

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
            serviceName = data.resolvedCompanyName ?? serviceName
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

    func submit(auth: AuthManager) async -> Bool {
        errorMessage = nil
        infoMessage = nil

        let normalizedEmail = email.trimmingCharacters(in: .whitespacesAndNewlines)
        let icoDigits = ico.filter(\.isNumber)
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
        if icoDigits.count != 8 {
            errorMessage = "IČO musí obsahovat přesně 8 číslic."
            return false
        }
        if serviceName.trimmingCharacters(in: .whitespacesAndNewlines).count < 2 {
            errorMessage = "Vyplňte název servisu."
            return false
        }
        if responsiblePerson.trimmingCharacters(in: .whitespacesAndNewlines).count < 2 {
            errorMessage = "Vyplňte zodpovědnou osobu."
            return false
        }
        if registrationPurpose.trimmingCharacters(in: .whitespacesAndNewlines).count < 10 {
            errorMessage = "Účel registrace musí mít alespoň 10 znaků."
            return false
        }

        isLoading = true
        defer { isLoading = false }

        do {
            let response = try await auth.requestServiceRegistration(
                ServiceRegistrationRequest(
                    email: normalizedEmail,
                    password: password,
                    ico: icoDigits,
                    serviceName: serviceName.trimmingCharacters(in: .whitespacesAndNewlines),
                    responsiblePerson: responsiblePerson.trimmingCharacters(in: .whitespacesAndNewlines),
                    phone: phone.trimmingCharacters(in: .whitespacesAndNewlines),
                    street: street.trimmingCharacters(in: .whitespacesAndNewlines),
                    streetNumber: normalize(streetNumber),
                    city: city.trimmingCharacters(in: .whitespacesAndNewlines),
                    zip: zip.trimmingCharacters(in: .whitespacesAndNewlines),
                    dic: normalize(dic),
                    registrationPurpose: registrationPurpose.trimmingCharacters(in: .whitespacesAndNewlines)
                )
            )
            infoMessage = response.message
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }

    private func normalize(_ value: String) -> String? {
        let cleaned = value.trimmingCharacters(in: .whitespacesAndNewlines)
        return cleaned.isEmpty ? nil : cleaned
    }
}
