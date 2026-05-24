import SwiftUI

struct AccountView: View {
    @EnvironmentObject private var env: AppEnvironment
    @EnvironmentObject private var viewModel: AccountViewModel

    @State private var draftName = ""
    @State private var draftPhone = ""
    @State private var draftCity = ""

    @State private var currentPassword = ""
    @State private var newPassword = ""
    @State private var totpCode = ""
    @State private var totpDisableCode = ""
    @State private var totpDisablePassword = ""
    @State private var localProtectionMessage: String?
    @State private var supportSubject = ""
    @State private var supportMessage = ""
    @State private var customCategoryName = ""
    @State private var customCategoryIcon = "🧩"
    @State private var isLicenseExpanded = false
    @State private var isSecurityExpanded = false
    @State private var isRecordsExpanded = false
    @State private var isPasswordExpanded = false
    @State private var isSupportExpanded = false
    @State private var isDataExpanded = false
    @State private var profileSavedMessage: String?

    var body: some View {
        NavigationStack {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: Theme.Spacing.lg) {
                    if viewModel.isLoading {
                        ProgressView()
                            .tint(.white)
                            .frame(maxWidth: .infinity)
                            .padding(.top, 60)
                    } else if let error = viewModel.error {
                        ErrorStateView(message: error) { Task { await reload() } }
                    } else {
                        profileHero
                        profileSection
                        quickOverviewRow
                        collapsibleSection(
                            title: "Licence",
                            subtitle: licenseSummaryLine,
                            icon: "creditcard.fill",
                            tint: Theme.Colors.primary,
                            isExpanded: $isLicenseExpanded
                        ) {
                            licenseSection
                        }
                        collapsibleSection(
                            title: "Zabezpečení",
                            subtitle: securitySummaryLine,
                            icon: "shield.lefthalf.filled",
                            tint: Theme.Colors.warning,
                            isExpanded: $isSecurityExpanded
                        ) {
                            securitySection
                        }
                        collapsibleSection(
                            title: "Konfigurace záznamů",
                            subtitle: recordsSummaryLine,
                            icon: "square.grid.2x2.fill",
                            tint: Theme.Colors.accent,
                            isExpanded: $isRecordsExpanded
                        ) {
                            recordConfigurationSection
                        }
                        collapsibleSection(
                            title: "Heslo",
                            subtitle: "Změna přístupového hesla",
                            icon: "key.fill",
                            tint: Theme.Colors.primaryDark,
                            isExpanded: $isPasswordExpanded
                        ) {
                            credentialsSection
                        }
                        collapsibleSection(
                            title: "Podpora",
                            subtitle: "Kontaktujte podporu přímo z aplikace",
                            icon: "bubble.left.and.bubble.right.fill",
                            tint: Theme.Colors.accent,
                            isExpanded: $isSupportExpanded
                        ) {
                            supportSection
                        }
                        collapsibleSection(
                            title: "Data a účet",
                            subtitle: "Export dat a destruktivní akce",
                            icon: "tray.full.fill",
                            tint: Theme.Colors.danger,
                            isExpanded: $isDataExpanded
                        ) {
                            dataSection
                        }

                        Button("Odhlásit se") {
                            env.authManager.logout()
                        }
                        .buttonStyle(PrimaryActionButtonStyle())
                    }
                }
                .padding(Theme.Spacing.md)
                .padding(.bottom, Theme.Spacing.xxl + 24)
            }
            .hubPageBackground()
            .navigationTitle("Profil")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarColorScheme(.dark, for: .navigationBar)
            .toolbarBackground(.hidden, for: .navigationBar)
            .task { await reload() }
        }
    }

    private var profileHero: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.md) {
            HStack(alignment: .center, spacing: Theme.Spacing.md) {
                Circle()
                    .fill(
                        LinearGradient(
                            colors: [Theme.Colors.primary, Theme.Colors.accent],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )
                    .frame(width: 84, height: 84)
                    .overlay {
                        Text(profileInitials)
                            .font(.system(size: 28, weight: .bold, design: .default))
                            .foregroundStyle(Theme.Colors.textOnLight)
                    }

                VStack(alignment: .leading, spacing: Theme.Spacing.xxs) {
                    Text("Profil")
                        .font(Theme.Typography.tiny)
                        .foregroundStyle(Theme.Colors.textSecondary)
                    Text(draftName.isEmpty ? (viewModel.profile?.name ?? "Váš účet") : draftName)
                        .font(Theme.Typography.sectionTitle)
                        .foregroundStyle(.white)
                        .fixedSize(horizontal: false, vertical: true)
                    Text(viewModel.profile?.email ?? "")
                        .font(Theme.Typography.caption)
                        .foregroundStyle(Theme.Colors.textSecondary)
                        .textSelection(.enabled)
                }

                Spacer(minLength: 0)
            }

            HStack(spacing: Theme.Spacing.sm) {
                summaryPill(label: "Licence", value: formattedPlan)
                summaryPill(label: "Vozidla", value: formattedVehicleLimit)
                summaryPill(label: "2FA", value: viewModel.security?.twoFactorEnabled == true ? "Aktivní" : "Vypnuto")
            }
        }
        .frame(maxWidth: .infinity)
        .padding(Theme.Spacing.md)
        .background(
            RoundedRectangle(cornerRadius: Theme.Radius.xl, style: .continuous)
                .fill(Theme.Colors.surface.opacity(0.95))
        )
        .overlay(
            RoundedRectangle(cornerRadius: Theme.Radius.xl, style: .continuous)
                .stroke(Theme.Colors.hairline, lineWidth: 1)
        )
    }

    private var quickOverviewRow: some View {
        HStack(spacing: Theme.Spacing.sm) {
            compactInfoCard(
                title: "Kontakt",
                value: effectivePhone.isEmpty ? "Bez telefonu" : effectivePhone,
                subtitle: effectiveCity.isEmpty ? "Doplňte město" : effectiveCity,
                icon: "phone.fill",
                tint: Theme.Colors.accent
            )
            compactInfoCard(
                title: "Role",
                value: localizedRole(viewModel.profile?.role ?? "user"),
                subtitle: formattedLicenseStatus,
                icon: "person.crop.circle.fill",
                tint: Theme.Colors.primaryDark
            )
        }
    }

    private var profileSection: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            accountSectionHeader(
                title: "Můj profil",
                subtitle: "Tady upravíte vše důležité pro svůj účet."
            )

            VStack(spacing: Theme.Spacing.sm) {
                TextField("Jméno a příjmení", text: $draftName)
                    .accountTextFieldStyle()

                TextField("Telefon", text: $draftPhone)
                    .accountTextFieldStyle()
                    .keyboardType(.phonePad)

                TextField("Město", text: $draftCity)
                    .accountTextFieldStyle()

                profileReadonlyRow(title: "E-mail", value: viewModel.profile?.email ?? "Neznámý e-mail")

                if let message = profileSavedMessage {
                    Text(message)
                        .font(Theme.Typography.captionStrong)
                        .foregroundStyle(Theme.Colors.textSecondary)
                }
            }

            Button("Uložit profil") {
                guard let token = env.authManager.token else { return }
                Task {
                    await viewModel.updateProfile(name: draftName, phone: draftPhone, city: draftCity, token: token)
                    await env.authManager.refreshProfile()
                    if viewModel.error == nil {
                        profileSavedMessage = "Profil byl uložen."
                    }
                }
            }
            .buttonStyle(PrimaryActionButtonStyle())
        }
        .hubDarkCard()
    }

    private var licenseSection: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            licenseLine(title: "Plán", value: viewModel.license?.plan.uppercased() ?? "-")
            licenseLine(title: "Stav", value: viewModel.license?.status ?? "-")
            licenseLine(
                title: "Vozidla",
                value: "\(viewModel.license?.vehiclesCurrent ?? 0) / \(viewModel.license?.isUnlimited == true ? "∞" : "\(viewModel.license?.vehiclesLimit ?? 0)")"
            )
        }
    }

    private var securitySection: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.md) {
            securityCard(
                title: "Ochrana této aplikace na tomto zařízení",
                subtitle: "Lokální odemčení aplikace pomocí \(env.appLockManager.localizedProtectionName) nebo kódu zařízení. Nechrání samotný účet na serveru."
            ) {
                VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
                    licenseLine(title: "Podporováno zařízením", value: env.appLockManager.deviceOwnerAuthAvailable ? "Ano" : "Ne")
                    licenseLine(title: "Povoleno uživatelem", value: env.appLockManager.localProtectionEnabled ? "Ano" : "Ne")
                    licenseLine(title: "Aktivní v aplikaci", value: localProtectionStatusLine)

                    Text("Po návratu do aplikace po cca 15 sekundách na pozadí se ochrana vyžádá znovu.")
                        .font(Theme.Typography.caption)
                        .foregroundStyle(Theme.Colors.textSecondary)
                    Text("Tato ochrana zamyká jen tuto aplikaci na tomto zařízení. Nejde o druhý faktor pro přihlášení k účtu.")
                        .font(Theme.Typography.caption)
                        .foregroundStyle(Theme.Colors.textSecondary)

                    HStack(spacing: Theme.Spacing.sm) {
                        Button(env.appLockManager.localProtectionEnabled ? "Aktualizovat ochranu" : "Zapnout ochranu aplikace") {
                            Task { await enableLocalProtection() }
                        }
                        .buttonStyle(PrimaryActionButtonStyle())
                        .disabled(!env.appLockManager.deviceOwnerAuthAvailable)

                        Button("Vypnout ochranu") {
                            Task { await disableLocalProtection() }
                        }
                        .buttonStyle(SecondaryActionButtonStyle())
                        .disabled(!env.appLockManager.localProtectionEnabled)
                    }

                    if env.appLockManager.localProtectionEnabled {
                        Button("Zamknout aplikaci hned") {
                            env.appLockManager.lockNow(isAuthenticated: env.authManager.isAuthenticated)
                        }
                        .buttonStyle(InlineChipButtonStyle(isSelected: false))
                    }

                    if let localProtectionMessage, !localProtectionMessage.isEmpty {
                        Text(localProtectionMessage)
                            .font(Theme.Typography.caption)
                            .foregroundStyle(Theme.Colors.textSecondary)
                    }
                }
            }

            securityCard(
                title: "Zabezpečení účtu",
                subtitle: "Dvoufázové ověření chrání přihlášení k účtu. Tato část je oddělená od lokálního odemčení aplikace."
            ) {
                VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
                    licenseLine(title: "Stav 2FA", value: viewModel.security?.twoFactorEnabled == true ? "Aktivní pro přihlášení" : "Vypnuté")
                    licenseLine(title: "TOTP klíč", value: viewModel.security?.totpConfigured == true ? "Připravený / nastavený" : "Ještě nevygenerovaný")
                    licenseLine(title: "Serverová evidence lokální ochrany", value: accountBiometricPreferenceLine)

                    Text("2FA = druhý faktor při přihlášení k účtu. Biometrie výše = jen lokální odemčení této aplikace na tomto telefonu.")
                        .font(Theme.Typography.caption)
                        .foregroundStyle(Theme.Colors.textSecondary)
                    Text("Backend zatím nepodporuje plné přihlášení k účtu přes Face ID / Touch ID bez zadání přihlašovacích údajů.")
                        .font(Theme.Typography.caption)
                        .foregroundStyle(Theme.Colors.textSecondary)

                    Button(viewModel.security?.totpConfigured == true ? "Vygenerovat nový 2FA klíč" : "Vygenerovat 2FA klíč") {
                        guard let token = env.authManager.token else { return }
                        Task { await viewModel.setupTotp(token: token) }
                    }
                    .buttonStyle(PrimaryActionButtonStyle())

                    if let setup = viewModel.totpSetup {
                        VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
                            Text("Secret")
                                .font(Theme.Typography.tiny)
                                .foregroundStyle(Theme.Colors.textSecondary)
                            Text(setup.secret)
                                .font(Theme.Typography.captionStrong)
                                .foregroundStyle(.white)
                                .textSelection(.enabled)
                            Text("OTPAuth URI")
                                .font(Theme.Typography.tiny)
                                .foregroundStyle(Theme.Colors.textSecondary)
                            Text(setup.otpauthUri)
                                .font(Theme.Typography.tiny)
                                .foregroundStyle(Theme.Colors.textSecondary)
                                .textSelection(.enabled)
                        }
                        .padding(Theme.Spacing.sm)
                        .background(Theme.Colors.elevated, in: RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous))
                    }

                    SecureField("6místný kód z autentikátoru", text: $totpCode)
                        .keyboardType(.numberPad)
                        .accountTextFieldStyle()

                    Button("Aktivovat 2FA") {
                        guard let token = env.authManager.token else { return }
                        Task { await viewModel.enableTotp(code: normalizedTotpCode, token: token) }
                    }
                    .buttonStyle(PrimaryActionButtonStyle())
                    .disabled(normalizedTotpCode.count != 6)

                    Divider().overlay(Theme.Colors.hairline)

                    SecureField("Současné heslo", text: $totpDisablePassword)
                        .accountTextFieldStyle()

                    SecureField("6místný kód pro vypnutí 2FA", text: $totpDisableCode)
                        .keyboardType(.numberPad)
                        .accountTextFieldStyle()

                    Button("Vypnout 2FA") {
                        guard let token = env.authManager.token else { return }
                        Task {
                            await viewModel.disableTotp(
                                currentPassword: totpDisablePassword,
                                code: normalizedTotpDisableCode,
                                token: token
                            )
                        }
                    }
                    .buttonStyle(SecondaryActionButtonStyle())
                    .disabled(totpDisablePassword.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || normalizedTotpDisableCode.count != 6)

                    if let message = viewModel.securityActionMessage {
                        Text(message)
                            .font(Theme.Typography.caption)
                            .foregroundStyle(Theme.Colors.textSecondary)
                    }
                }
            }
        }
    }

    private var recordConfigurationSection: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            VStack(spacing: Theme.Spacing.sm) {
                HStack(spacing: Theme.Spacing.sm) {
                    TextField("Ikona", text: $customCategoryIcon)
                        .accountTextFieldStyle()
                        .frame(width: 84)

                    TextField("Nová kategorie", text: $customCategoryName)
                        .accountTextFieldStyle()
                }

                Button("Přidat kategorii") {
                    env.recordConfigurationStore.addCategory(
                        label: customCategoryName,
                        icon: customCategoryIcon.isEmpty ? "🧩" : customCategoryIcon
                    )
                    customCategoryName = ""
                    customCategoryIcon = "🧩"
                }
                .buttonStyle(SecondaryActionButtonStyle())
                .disabled(customCategoryName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }

            if !env.recordConfigurationStore.customCategories.isEmpty {
                VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
                    Text("Moje kategorie")
                        .font(Theme.Typography.captionStrong)
                        .foregroundStyle(.white)

                    ForEach(env.recordConfigurationStore.customCategories) { category in
                        HStack(spacing: Theme.Spacing.sm) {
                            Text(category.icon)
                                .font(.system(size: 20))
                                .frame(width: 36, height: 36)
                                .background(Theme.Colors.elevated, in: RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous))

                            VStack(alignment: .leading, spacing: 2) {
                                Text(category.label)
                                    .font(Theme.Typography.bodyStrong)
                                    .foregroundStyle(.white)
                                Text(category.id)
                                    .font(Theme.Typography.tiny)
                                    .foregroundStyle(Theme.Colors.textSecondary)
                            }

                            Spacer()

                            Button(role: .destructive) {
                                env.recordConfigurationStore.deleteCategory(id: category.id)
                            } label: {
                                Image(systemName: "trash")
                            }
                            .buttonStyle(.plain)
                            .foregroundStyle(Theme.Colors.danger)
                        }
                        .padding(Theme.Spacing.sm)
                        .background(Theme.Colors.elevated, in: RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous))
                    }
                }
            }

            if !env.recordConfigurationStore.customTemplates.isEmpty {
                VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
                    Text("Moje šablony")
                        .font(Theme.Typography.captionStrong)
                        .foregroundStyle(.white)

                    ForEach(env.recordConfigurationStore.customTemplates) { template in
                        HStack(spacing: Theme.Spacing.sm) {
                            Text(template.icon)
                                .font(.system(size: 20))
                                .frame(width: 36, height: 36)
                                .background(Theme.Colors.elevated, in: RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous))

                            VStack(alignment: .leading, spacing: 2) {
                                Text(template.name)
                                    .font(Theme.Typography.bodyStrong)
                                    .foregroundStyle(.white)
                                Text(template.templateDescription ?? "Bez popisu")
                                    .font(Theme.Typography.tiny)
                                    .foregroundStyle(Theme.Colors.textSecondary)
                                    .lineLimit(2)
                            }

                            Spacer()

                            Button(role: .destructive) {
                                env.recordConfigurationStore.deleteTemplate(template)
                            } label: {
                                Image(systemName: "trash")
                            }
                            .buttonStyle(.plain)
                            .foregroundStyle(Theme.Colors.danger)
                        }
                        .padding(Theme.Spacing.sm)
                        .background(Theme.Colors.elevated, in: RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous))
                    }
                }
            }
        }
    }

    private var credentialsSection: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            SecureField("Současné heslo", text: $currentPassword)
                .accountTextFieldStyle()
            SecureField("Nové heslo", text: $newPassword)
                .accountTextFieldStyle()

            Button("Změnit heslo") {
                guard let token = env.authManager.token else { return }
                Task { await viewModel.changePassword(current: currentPassword, new: newPassword, token: token) }
            }
            .buttonStyle(PrimaryActionButtonStyle())
        }
    }

    private var supportSection: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            TextField("Předmět", text: $supportSubject)
                .accountTextFieldStyle()

            TextField("Zpráva", text: $supportMessage, axis: .vertical)
                .lineLimit(3...6)
                .accountTextFieldStyle()

            Button("Odeslat na podporu") {
                guard let token = env.authManager.token else { return }
                Task {
                    await viewModel.sendSupport(
                        category: "obecne",
                        subject: supportSubject,
                        message: supportMessage,
                        phone: draftPhone,
                        token: token
                    )
                }
            }
            .buttonStyle(PrimaryActionButtonStyle())
        }
    }

    private var dataSection: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            Button("Stáhnout export dat") {
                guard let token = env.authManager.token else { return }
                Task { await viewModel.downloadExport(token: token) }
            }
            .buttonStyle(PrimaryActionButtonStyle())

            if let exportURL = viewModel.exportURL {
                ShareLink(item: exportURL) {
                    Text("Sdílet export")
                        .font(Theme.Typography.captionStrong)
                        .foregroundStyle(.white)
                }
            }

            Button("Smazat účet") {
                guard let token = env.authManager.token else { return }
                Task {
                    await viewModel.deleteAccount(password: currentPassword, token: token)
                    env.authManager.logout()
                }
            }
            .buttonStyle(SecondaryActionButtonStyle())
        }
    }

    private var profileInitials: String {
        let source = (draftName.isEmpty ? (viewModel.profile?.name ?? "TU") : draftName)
        let parts = source
            .split(separator: " ")
            .prefix(2)
            .map { String($0.prefix(1)).uppercased() }
            .joined()

        return parts.isEmpty ? "TU" : parts
    }

    private var formattedPlan: String {
        viewModel.license?.plan.uppercased() ?? "FREE"
    }

    private var formattedLicenseStatus: String {
        viewModel.license?.status ?? "Neznámý stav"
    }

    private var formattedVehicleLimit: String {
        "\(viewModel.license?.vehiclesCurrent ?? 0) / \(viewModel.license?.isUnlimited == true ? "∞" : "\(viewModel.license?.vehiclesLimit ?? 0)")"
    }

    private var effectivePhone: String {
        draftPhone.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private var effectiveCity: String {
        draftCity.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private var licenseSummaryLine: String {
        "\(formattedPlan) • \(formattedLicenseStatus)"
    }

    private var securitySummaryLine: String {
        let twoFactor = viewModel.security?.twoFactorEnabled == true ? "účet chráněn 2FA" : "2FA vypnuté"
        let localApp = env.appLockManager.localProtectionEnabled ? "aplikace zamčená lokálně" : "bez lokální ochrany"
        return "\(twoFactor), \(localApp)"
    }

    private var normalizedTotpCode: String {
        totpCode.filter(\.isNumber)
    }

    private var normalizedTotpDisableCode: String {
        totpDisableCode.filter(\.isNumber)
    }

    private var localProtectionStatusLine: String {
        if !env.appLockManager.deviceOwnerAuthAvailable {
            return "Zařízení nepodporováno"
        }
        if !env.appLockManager.localProtectionEnabled {
            return "Neaktivní"
        }
        return env.appLockManager.isLocked ? "Čeká na odemknutí" : "Aktivní při otevření aplikace"
    }

    private var accountBiometricPreferenceLine: String {
        viewModel.security?.biometricEnabled == true ? "Uloženo jen jako preference tohoto zařízení" : "Neuloženo"
    }

    private var recordsSummaryLine: String {
        let categories = env.recordConfigurationStore.customCategories.count
        let templates = env.recordConfigurationStore.customTemplates.count
        return "\(categories) kategorií • \(templates) šablon"
    }

    private func licenseLine(title: String, value: String) -> some View {
        HStack {
            Text(title)
                .font(Theme.Typography.caption)
                .foregroundStyle(Theme.Colors.textSecondary)
            Spacer()
            Text(value)
                .font(Theme.Typography.captionStrong)
                .foregroundStyle(.white)
        }
    }

    private func localizedRole(_ role: String) -> String {
        switch role.lowercased() {
        case "developer_admin":
            return "Developer"
        case "admin":
            return "Admin"
        case "service":
            return "Servis"
        default:
            return "Uživatel"
        }
    }

    private func securityCard<Content: View>(title: String, subtitle: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            accountSectionHeader(title: title, subtitle: subtitle)
            content()
        }
        .padding(Theme.Spacing.sm)
        .background(Theme.Colors.elevated, in: RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous))
    }

    private func accountSectionHeader(title: String, subtitle: String) -> some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.xxs) {
            Text(title)
                .font(Theme.Typography.cardTitle)
                .foregroundStyle(.white)
            Text(subtitle)
                .font(Theme.Typography.caption)
                .foregroundStyle(Theme.Colors.textSecondary)
        }
    }

    private func compactInfoCard(title: String, value: String, subtitle: String, icon: String, tint: Color) -> some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
            HStack {
                Image(systemName: icon)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(tint)
                    .frame(width: 30, height: 30)
                    .background(tint.opacity(0.16), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                Spacer(minLength: 0)
            }

            Text(title)
                .font(Theme.Typography.tiny)
                .foregroundStyle(Theme.Colors.textSecondary)
            Text(value)
                .font(Theme.Typography.bodyStrong)
                .foregroundStyle(.white)
                .lineLimit(1)
                .minimumScaleFactor(0.8)
            Text(subtitle)
                .font(Theme.Typography.caption)
                .foregroundStyle(Theme.Colors.textSecondary)
                .lineLimit(2)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(Theme.Spacing.md)
        .background(
            RoundedRectangle(cornerRadius: Theme.Radius.lg, style: .continuous)
                .fill(Theme.Colors.surface.opacity(0.95))
        )
        .overlay(
            RoundedRectangle(cornerRadius: Theme.Radius.lg, style: .continuous)
                .stroke(Theme.Colors.hairline, lineWidth: 1)
        )
    }

    private func summaryPill(label: String, value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(Theme.Typography.tiny)
                .foregroundStyle(Theme.Colors.textSecondary)
            Text(value)
                .font(Theme.Typography.captionStrong)
                .foregroundStyle(.white)
                .lineLimit(1)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, Theme.Spacing.sm)
        .padding(.vertical, Theme.Spacing.xs)
        .background(Theme.Colors.elevated, in: RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous))
    }

    private func profileReadonlyRow(title: String, value: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(Theme.Typography.tiny)
                .foregroundStyle(Theme.Colors.textSecondary)
            Text(value)
                .font(Theme.Typography.bodyStrong)
                .foregroundStyle(.white)
                .textSelection(.enabled)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.horizontal, Theme.Spacing.sm)
                .padding(.vertical, 12)
                .background(
                    RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous)
                        .fill(Theme.Colors.elevated)
                )
        }
    }

    private func collapsibleSection<Content: View>(
        title: String,
        subtitle: String,
        icon: String,
        tint: Color,
        isExpanded: Binding<Bool>,
        @ViewBuilder content: @escaping () -> Content
    ) -> some View {
        DisclosureGroup(isExpanded: isExpanded) {
            VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
                Divider().overlay(Theme.Colors.hairline)
                content()
            }
            .padding(.top, Theme.Spacing.sm)
        } label: {
            HStack(spacing: Theme.Spacing.sm) {
                Image(systemName: icon)
                    .font(.headline.weight(.semibold))
                    .foregroundStyle(tint)
                    .frame(width: 38, height: 38)
                    .background(tint.opacity(0.14), in: RoundedRectangle(cornerRadius: 12, style: .continuous))

                VStack(alignment: .leading, spacing: 2) {
                    Text(title)
                        .font(Theme.Typography.bodyStrong)
                        .foregroundStyle(.white)
                    Text(subtitle)
                        .font(Theme.Typography.caption)
                        .foregroundStyle(Theme.Colors.textSecondary)
                        .lineLimit(2)
                }

                Spacer(minLength: 0)
            }
            .contentShape(Rectangle())
        }
        .tint(.white)
        .hubDarkCard()
    }

    private func reload(force: Bool = false) async {
        guard let token = env.authManager.token else { return }
        await viewModel.loadIfNeeded(token: token, force: force)
        draftName = viewModel.profile?.name ?? ""
        draftPhone = viewModel.profile?.phone ?? ""
        draftCity = viewModel.profile?.city ?? ""
        profileSavedMessage = nil
    }

    private func enableLocalProtection() async {
        do {
            try await env.appLockManager.enableLocalProtection()
            localProtectionMessage = "Ochrana aplikace je aktivní. Při otevření použijete \(env.appLockManager.localizedProtectionName) nebo kód zařízení."
            if let token = env.authManager.token {
                await viewModel.updateBiometric(enabled: true, preferred: true, token: token)
            }
        } catch {
            localProtectionMessage = UserFacingErrorMapper.message(
                for: error,
                context: .localProtection,
                fallback: "Lokální ochranu aplikace se nepodařilo zapnout."
            )
        }
    }

    private func disableLocalProtection() async {
        do {
            try await env.appLockManager.disableLocalProtection()
            localProtectionMessage = "Lokální ochrana aplikace na tomto zařízení byla vypnuta."
            if let token = env.authManager.token {
                await viewModel.updateBiometric(enabled: false, preferred: false, token: token)
            }
        } catch {
            localProtectionMessage = UserFacingErrorMapper.message(
                for: error,
                context: .localProtection,
                fallback: "Lokální ochranu aplikace se nepodařilo vypnout."
            )
        }
    }
}

private struct AccountTextFieldModifier: ViewModifier {
    func body(content: Content) -> some View {
        content
            .font(Theme.Typography.body)
            .foregroundColor(.white)
            .tint(.white)
            .padding(.horizontal, Theme.Spacing.sm)
            .padding(.vertical, 12)
            .background(
                RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous)
                    .fill(Theme.Colors.inputSurface)
            )
            .overlay(
                RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous)
                    .stroke(Theme.Colors.textSecondary.opacity(0.18), lineWidth: 1)
            )
            .environment(\.colorScheme, .dark)
    }
}

private extension View {
    func accountTextFieldStyle() -> some View {
        modifier(AccountTextFieldModifier())
    }
}
