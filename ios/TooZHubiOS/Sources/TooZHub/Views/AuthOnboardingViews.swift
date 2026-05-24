import SwiftUI

struct UserRegistrationView: View {
    @EnvironmentObject private var env: AppEnvironment
    @Environment(\.dismiss) private var dismiss
    @StateObject private var viewModel = RegisterViewModel()

    var body: some View {
        NavigationStack {
            Form {
                Section("Přístup") {
                    TextField("E-mail", text: $viewModel.email)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled(true)
                        .keyboardType(.emailAddress)
                    SecureField("Heslo", text: $viewModel.password)
                    SecureField("Potvrzení hesla", text: $viewModel.passwordConfirm)
                }

                Section("Profil") {
                    TextField("Jméno / Název", text: $viewModel.name)
                    HStack {
                        TextField("IČO (podnikatel)", text: $viewModel.ico)
                            .keyboardType(.numberPad)
                        Button("ARES") {
                            Task { await viewModel.lookupAres(auth: env.authManager) }
                        }
                        .disabled(viewModel.ico.filter(\.isNumber).count != 8 || viewModel.isLoading)
                    }
                    TextField("DIČ", text: $viewModel.dic)
                    TextField("Ulice", text: $viewModel.street)
                    TextField("Číslo popisné", text: $viewModel.streetNumber)
                    TextField("Město", text: $viewModel.city)
                    TextField("PSČ", text: $viewModel.zip)
                    TextField("Telefon", text: $viewModel.phone)
                        .keyboardType(.phonePad)
                }

                if let info = viewModel.infoMessage {
                    Section {
                        Text(info)
                            .foregroundStyle(Theme.Colors.accent)
                    }
                }
                if let error = viewModel.errorMessage {
                    Section {
                        Text(error)
                            .foregroundStyle(.red)
                    }
                }
            }
            .navigationTitle("Registrace uživatele")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Zrušit") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Registrovat") {
                        Task {
                            let ok = await viewModel.registerUser(auth: env.authManager)
                            if ok { dismiss() }
                        }
                    }
                    .disabled(viewModel.isLoading)
                }
            }
        }
    }
}

struct ServiceRegistrationView: View {
    @EnvironmentObject private var env: AppEnvironment
    @Environment(\.dismiss) private var dismiss
    @StateObject private var viewModel = ServiceRegistrationViewModel()

    var body: some View {
        NavigationStack {
            Form {
                Section("Přístup") {
                    TextField("E-mail", text: $viewModel.email)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled(true)
                        .keyboardType(.emailAddress)
                    SecureField("Heslo", text: $viewModel.password)
                    SecureField("Potvrzení hesla", text: $viewModel.passwordConfirm)
                }

                Section("Servisní profil") {
                    HStack {
                        TextField("IČO", text: $viewModel.ico)
                            .keyboardType(.numberPad)
                        Button("ARES") {
                            Task { await viewModel.lookupAres(auth: env.authManager) }
                        }
                        .disabled(viewModel.ico.filter(\.isNumber).count != 8 || viewModel.isLoading)
                    }
                    TextField("Název servisu", text: $viewModel.serviceName)
                    TextField("Zodpovědná osoba", text: $viewModel.responsiblePerson)
                    TextField("Telefon", text: $viewModel.phone)
                        .keyboardType(.phonePad)
                    TextField("Ulice", text: $viewModel.street)
                    TextField("Číslo popisné", text: $viewModel.streetNumber)
                    TextField("Město", text: $viewModel.city)
                    TextField("PSČ", text: $viewModel.zip)
                    TextField("DIČ", text: $viewModel.dic)
                    TextField("Účel registrace", text: $viewModel.registrationPurpose, axis: .vertical)
                        .lineLimit(3...6)
                }

                if let info = viewModel.infoMessage {
                    Section {
                        Text(info)
                            .foregroundStyle(Theme.Colors.accent)
                    }
                }
                if let error = viewModel.errorMessage {
                    Section {
                        Text(error)
                            .foregroundStyle(.red)
                    }
                }
            }
            .navigationTitle("Žádost o servisní účet")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Zrušit") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Odeslat") {
                        Task {
                            let ok = await viewModel.submit(auth: env.authManager)
                            if ok { dismiss() }
                        }
                    }
                    .disabled(viewModel.isLoading)
                }
            }
        }
    }
}

struct ForgotPasswordView: View {
    @EnvironmentObject private var env: AppEnvironment
    @Environment(\.dismiss) private var dismiss
    @StateObject private var viewModel = ForgotPasswordViewModel()

    var body: some View {
        NavigationStack {
            Form {
                Section("Účet") {
                    TextField("E-mail", text: $viewModel.email)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled(true)
                        .keyboardType(.emailAddress)
                }

                if let info = viewModel.infoMessage {
                    Section {
                        Text(info)
                            .foregroundStyle(Theme.Colors.accent)
                    }
                }
                if let resetURL = viewModel.resetURL, let url = URL(string: resetURL) {
                    Section("Testovací odkaz") {
                        Link(resetURL, destination: url)
                            .font(.footnote)
                            .lineLimit(3)
                    }
                }
                if let error = viewModel.errorMessage {
                    Section {
                        Text(error)
                            .foregroundStyle(.red)
                    }
                }
            }
            .navigationTitle("Obnova hesla")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Zavřít") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Odeslat") {
                        Task { await viewModel.submit(auth: env.authManager) }
                    }
                    .disabled(viewModel.isLoading)
                }
            }
        }
    }
}
