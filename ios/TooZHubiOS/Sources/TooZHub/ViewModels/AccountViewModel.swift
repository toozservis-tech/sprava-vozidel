import Foundation

@MainActor
final class AccountViewModel: ObservableObject {
    @Published var profile: UserProfile?
    @Published var security: SecuritySettingsResponse?
    @Published var license: LicenseStatus?
    @Published var exportURL: URL?
    @Published var isLoading = false
    @Published var error: String?
    @Published var securityActionMessage: String?
    @Published var totpSetup: TotpSetupResponse?

    private let service: AccountService
    private let featureService: UserFeatureService
    private var hasLoadedOnce = false
    private var lastLoadedAt: Date?
    private let reloadTTL: TimeInterval = 60

    init(service: AccountService, featureService: UserFeatureService) {
        self.service = service
        self.featureService = featureService
    }

    func loadIfNeeded(token: String, force: Bool = false) async {
        if !force,
           hasLoadedOnce,
           let lastLoadedAt,
           Date().timeIntervalSince(lastLoadedAt) < reloadTTL {
            return
        }
        await load(token: token)
    }

    func load(token: String) async {
        isLoading = true
        error = nil
        defer { isLoading = false }

        do {
            async let profile = service.fetchProfile(token: token)
            async let security = service.fetchSecuritySettings(token: token)
            async let license = service.fetchLicense(token: token)

            self.profile = try await profile
            self.security = try await security
            self.license = try await license
            hasLoadedOnce = true
            lastLoadedAt = Date()
        } catch {
            self.error = userFacingMessage(for: error, fallback: "Nepodařilo se načíst profil a bezpečnostní nastavení.")
        }
    }

    func setupTotp(token: String) async {
        error = nil
        securityActionMessage = nil
        do {
            let payload = try await service.setupTotp(token: token)
            totpSetup = payload
            securityActionMessage = payload.message
            await load(token: token)
        } catch {
            self.error = userFacingMessage(for: error, fallback: "Nepodařilo se připravit 2FA klíč.")
        }
    }

    func enableTotp(code: String, token: String) async {
        error = nil
        securityActionMessage = nil
        do {
            let response = try await service.enableTotp(code: code, token: token)
            securityActionMessage = response.message
            await load(token: token)
        } catch {
            self.error = userFacingMessage(for: error, fallback: "2FA se nepodařilo aktivovat. Zkontrolujte ověřovací kód.")
        }
    }

    func disableTotp(currentPassword: String, code: String, token: String) async {
        error = nil
        securityActionMessage = nil
        do {
            let response = try await service.disableTotp(currentPassword: currentPassword, code: code, token: token)
            securityActionMessage = response.message
            totpSetup = nil
            await load(token: token)
        } catch {
            self.error = userFacingMessage(for: error, fallback: "2FA se nepodařilo vypnout. Zkontrolujte heslo a ověřovací kód.")
        }
    }

    func updateBiometric(enabled: Bool, preferred: Bool?, token: String) async {
        error = nil
        securityActionMessage = nil
        do {
            let response = try await service.updateBiometricPreference(enabled: enabled, preferred: preferred, token: token)
            securityActionMessage = response.message
            await load(token: token)
        } catch {
            self.error = userFacingMessage(for: error, fallback: "Nastavení biometrie se nepodařilo uložit.")
        }
    }

    func updateProfile(name: String, phone: String, city: String, token: String) async {
        do {
            profile = try await service.updateProfile(
                UserUpdateRequest(name: name, phone: phone, city: city, street: nil, streetNumber: nil, zip: nil),
                token: token
            )
        } catch {
            self.error = userFacingMessage(for: error, fallback: "Profil se nepodařilo uložit.")
        }
    }

    func changePassword(current: String, new: String, token: String) async {
        do {
            try await featureService.changePassword(ChangePasswordRequest(currentPassword: current, newPassword: new), token: token)
        } catch {
            self.error = userFacingMessage(for: error, fallback: "Heslo se nepodařilo změnit.")
        }
    }

    func sendSupport(category: String, subject: String, message: String, phone: String?, token: String) async {
        do {
            try await featureService.sendSupport(
                SupportRequest(
                    category: category,
                    subject: subject,
                    message: message,
                    phone: phone,
                    includeDiagnostics: true,
                    pageUrl: nil,
                    userAgent: nil
                ),
                token: token
            )
        } catch {
            self.error = userFacingMessage(for: error, fallback: "Zprávu podpoře se nepodařilo odeslat.")
        }
    }

    func downloadExport(token: String) async {
        do {
            exportURL = try await featureService.downloadExport(token: token)
        } catch {
            self.error = userFacingMessage(for: error, fallback: "Export dat se nepodařilo připravit.")
        }
    }

    func deleteAccount(password: String, token: String) async {
        do {
            try await featureService.deleteAccount(
                DeleteAccountRequest(currentPassword: password, confirmationText: "SMAZAT UCET", exportDownloaded: true),
                token: token
            )
        } catch {
            self.error = userFacingMessage(for: error, fallback: "Účet se nepodařilo smazat.")
        }
    }

    private func userFacingMessage(for error: Error, fallback: String) -> String {
#if DEBUG
        print("[AccountViewModel] \(error.localizedDescription)")
#endif
        return UserFacingErrorMapper.message(for: error, context: .account, fallback: fallback)
    }
}
