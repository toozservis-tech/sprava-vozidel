import SwiftUI

struct LoginView: View {
    @EnvironmentObject private var env: AppEnvironment
    @StateObject private var viewModel = LoginViewModel()
    @State private var showUserRegistration = false
    @State private var showServiceRegistration = false
    @State private var showForgotPassword = false
    @State private var privilegedRoleUnlocked = false

    var body: some View {
        NavigationStack {
            GeometryReader { proxy in
                let horizontalPadding = Theme.Spacing.lg
                let contentWidth = max(280, min(560, proxy.size.width - (horizontalPadding * 2)))
                ZStack {
                    Theme.Colors.pageGradient
                        .ignoresSafeArea()
                    Circle()
                        .fill(.white.opacity(0.16))
                        .frame(width: 260, height: 260)
                        .blur(radius: 6)
                        .offset(x: -140, y: -280)
                    Circle()
                        .fill(.white.opacity(0.12))
                        .frame(width: 220, height: 220)
                        .blur(radius: 8)
                        .offset(x: 150, y: -220)

                    ScrollView {
                        VStack(alignment: .leading, spacing: Theme.Spacing.md) {
                            BrandBadge()
                                .contentShape(Rectangle())
#if DEBUG
                                .onTapGesture(count: 7) {
                                    privilegedRoleUnlocked.toggle()
                                    env.authManager.setPrivilegedLoginEnabled(privilegedRoleUnlocked)
                                    if !privilegedRoleUnlocked && (viewModel.expectedRole == "admin" || viewModel.expectedRole == "developer_admin") {
                                        viewModel.expectedRole = "user"
                                    }
                                }
#endif
                            Text("Přihlášení do účtu")
                                .font(Theme.Typography.title)
                                .foregroundStyle(.white)
                            Text("Jedno místo pro vozidla, servisní historii, rezervace i připomínky.")
                                .font(Theme.Typography.body)
                                .foregroundStyle(.white.opacity(0.8))
                                .fixedSize(horizontal: false, vertical: true)
                            HStack(spacing: Theme.Spacing.xs) {
                                featurePill(icon: "shield.checkered", text: "Bezpečné")
                                featurePill(icon: "clock.badge.checkmark", text: "Přehledné")
                                featurePill(icon: "wrench.and.screwdriver.fill", text: "Pro servis")
                            }
                            HStack(spacing: Theme.Spacing.sm) {
                                Image(systemName: "sparkles")
                                    .font(.system(size: 18, weight: .semibold))
                                VStack(alignment: .leading, spacing: 4) {
                                    Text("Vše probíhá v aplikaci")
                                        .font(.system(size: 14, weight: .semibold))
                                    Text("Novinky, změny i správa funkcí jsou dostupné přímo po přihlášení.")
                                        .font(.system(size: 12, weight: .regular))
                                        .foregroundStyle(.white.opacity(0.86))
                                }
                                Spacer(minLength: 8)
                            }
                            .foregroundStyle(.white)
                            .padding(Theme.Spacing.sm)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(
                                LinearGradient(
                                    colors: [
                                        Theme.Colors.primaryDark.opacity(0.9),
                                        Theme.Colors.surface.opacity(0.82)
                                    ],
                                    startPoint: .topLeading,
                                    endPoint: .bottomTrailing
                                ),
                                in: RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous)
                            )
                            .overlay(
                                RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous)
                                    .stroke(.white.opacity(0.16), lineWidth: 1)
                            )
                            #if DEBUG
                            if privilegedRoleUnlocked {
                                Text("Skrytý režim aktivní")
                                    .font(.caption2.weight(.semibold))
                                    .foregroundStyle(.yellow)
                            }
                            #endif
                        }
                        .frame(width: contentWidth, alignment: .leading)

                        VStack(spacing: Theme.Spacing.sm) {
                            #if DEBUG
                            if privilegedRoleUnlocked {
                                Picker("Role", selection: $viewModel.expectedRole) {
                                    Text("Uživatel").tag("user")
                                    Text("Servis").tag("service")
                                    Text("Admin").tag("admin")
                                    Text("Developer").tag("developer_admin")
                                }
                                .pickerStyle(.menu)
                            } else {
                                Picker("Role", selection: $viewModel.expectedRole) {
                                    Text("Uživatel").tag("user")
                                    Text("Servis").tag("service")
                                }
                                .pickerStyle(.segmented)
                            }
                            #else
                            Picker("Role", selection: $viewModel.expectedRole) {
                                Text("Uživatel").tag("user")
                                Text("Servis").tag("service")
                            }
                            .pickerStyle(.segmented)
                            #endif

                            TextField("Email", text: $viewModel.email)
                                .textContentType(.emailAddress)
                                .keyboardType(.emailAddress)
                                .autocapitalization(.none)
                                .foregroundStyle(.black)
                                .tint(Theme.Colors.primary)
                                .padding()
                                .frame(maxWidth: .infinity)
                                .background(Color.white.opacity(0.9), in: RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous))

                            SecureField("Heslo", text: $viewModel.password)
                                .textContentType(.password)
                                .foregroundStyle(.black)
                                .tint(Theme.Colors.primary)
                                .padding()
                                .frame(maxWidth: .infinity)
                                .background(Color.white.opacity(0.9), in: RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous))

                            if viewModel.challengeToken != nil {
                                SecureField("2FA kód", text: $viewModel.twoFactorCode)
                                    .keyboardType(.numberPad)
                                    .foregroundStyle(.black)
                                    .tint(Theme.Colors.primary)
                                    .padding()
                                    .frame(maxWidth: .infinity)
                                    .background(Color.white.opacity(0.9), in: RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous))
                            }

                            if let error = viewModel.errorMessage {
                                Text(error)
                                    .font(Theme.Typography.caption)
                                    .foregroundStyle(.red)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                            }

                            Button {
                                Task {
                                    if viewModel.challengeToken == nil {
                                        await viewModel.signIn(auth: env.authManager)
                                    } else {
                                        await viewModel.verify2FA(auth: env.authManager)
                                    }
                                }
                            } label: {
                                HStack(spacing: Theme.Spacing.xs) {
                                    if viewModel.isLoading {
                                        ProgressView()
                                            .tint(.white)
                                    }
                                    Text(viewModel.challengeToken == nil ? "Přihlásit se" : "Ověřit 2FA")
                                }
                                .frame(maxWidth: .infinity)
                            }
                            .buttonStyle(PrimaryActionButtonStyle())
                            .disabled(viewModel.isLoading)

                            HStack(spacing: Theme.Spacing.sm) {
                                Button("Registrace uživatele") {
                                    showUserRegistration = true
                                }
                                .buttonStyle(SecondaryActionButtonStyle())

                                Button("Servisní registrace") {
                                    showServiceRegistration = true
                                }
                                .buttonStyle(SecondaryActionButtonStyle())
                            }

                            Button("Zapomenuté heslo") {
                                showForgotPassword = true
                            }
                            .font(Theme.Typography.caption)
                            .foregroundStyle(.white.opacity(0.9))
                        }
                        .padding(Theme.Spacing.md)
                        .frame(width: contentWidth)
                        .glassStyle()
                        .padding(.top, Theme.Spacing.lg)
                        .padding(.bottom, Theme.Spacing.lg)
                        .frame(maxWidth: .infinity)
                    }
                    .scrollIndicators(.hidden)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                }
            }
            .scrollDismissesKeyboard(.interactively)
            .toolbar(.hidden, for: .navigationBar)
            .sheet(isPresented: $showUserRegistration) {
                UserRegistrationView()
                    .environmentObject(env)
            }
            .sheet(isPresented: $showServiceRegistration) {
                ServiceRegistrationView()
                    .environmentObject(env)
            }
            .sheet(isPresented: $showForgotPassword) {
                ForgotPasswordView()
                    .environmentObject(env)
            }
        }
    }

    private func featurePill(icon: String, text: String) -> some View {
        HStack(spacing: 5) {
            Image(systemName: icon)
            Text(text)
        }
        .font(.system(size: 11, weight: .semibold))
        .foregroundStyle(.white.opacity(0.9))
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .background(.white.opacity(0.12), in: Capsule())
    }
}
