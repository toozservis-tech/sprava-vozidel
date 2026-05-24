import Foundation
import LocalAuthentication
import SwiftUI

@MainActor
final class AppLockManager: ObservableObject {
    enum LockState: Equatable {
        case unavailable
        case unlocked
        case locked
        case unlocking
    }

    private enum StorageKeys {
        static let localProtectionEnabled = "local_app_protection_enabled"
    }

    @Published private(set) var lockState: LockState = .unlocked
    @Published private(set) var biometryType: LABiometryType = .none
    @Published private(set) var deviceOwnerAuthAvailable = false
    @Published private(set) var lastErrorMessage: String?

    private var lastBackgroundAt: Date?
    private let relockDelay: TimeInterval = 15

    var localProtectionEnabled: Bool {
        get { UserDefaults.standard.bool(forKey: StorageKeys.localProtectionEnabled) }
        set { UserDefaults.standard.set(newValue, forKey: StorageKeys.localProtectionEnabled) }
    }

    var isLocked: Bool {
        lockState == .locked || lockState == .unlocking
    }

    var localizedProtectionName: String {
        switch biometryType {
        case .faceID:
            return "Face ID"
        case .touchID:
            return "Touch ID"
        default:
            return "Biometrie"
        }
    }

    var deviceProtectionSummary: String {
        if !deviceOwnerAuthAvailable {
            return "Toto zařízení nepodporuje biometrické odemykání ani ověření kódem zařízení."
        }
        switch biometryType {
        case .faceID, .touchID:
            return "\(localizedProtectionName) je na zařízení dostupné a aplikace může při odemykání použít i kód zařízení."
        default:
            return "Aplikace může použít ověření vlastníka zařízení pomocí systémového kódu."
        }
    }

    init() {
        refreshCapabilities()
        if !deviceOwnerAuthAvailable {
            localProtectionEnabled = false
            lockState = .unavailable
        }
    }

    func refreshCapabilities() {
        let context = LAContext()
        var error: NSError?
        let canEvaluateOwner = context.canEvaluatePolicy(.deviceOwnerAuthentication, error: &error)
        deviceOwnerAuthAvailable = canEvaluateOwner

        var bioError: NSError?
        _ = context.canEvaluatePolicy(.deviceOwnerAuthenticationWithBiometrics, error: &bioError)
        biometryType = context.biometryType

        if !canEvaluateOwner {
            lockState = .unavailable
        } else if !localProtectionEnabled {
            lockState = .unlocked
        }
    }

    func updateScenePhase(_ phase: ScenePhase, isAuthenticated: Bool) {
        guard isAuthenticated else {
            lockState = .unlocked
            lastBackgroundAt = nil
            return
        }
        guard localProtectionEnabled, deviceOwnerAuthAvailable else { return }

        switch phase {
        case .background, .inactive:
            lastBackgroundAt = Date()
        case .active:
            let shouldRelock: Bool
            if let lastBackgroundAt {
                shouldRelock = Date().timeIntervalSince(lastBackgroundAt) >= relockDelay
            } else {
                shouldRelock = true
            }
            if shouldRelock {
                lockState = .locked
            }
        @unknown default:
            break
        }
    }

    func enableLocalProtection() async throws {
        refreshCapabilities()
        guard deviceOwnerAuthAvailable else {
            throw APIError.serverError("Zařízení nepodporuje bezpečné odemykání pomocí biometrie ani kódu zařízení.")
        }
        let success = try await authenticateUser(reason: "Zapněte ochranu aplikace při otevření.")
        guard success else {
            throw APIError.serverError("Ověření zařízení se nepodařilo dokončit.")
        }
        localProtectionEnabled = true
        lockState = .unlocked
        lastErrorMessage = nil
    }

    func disableLocalProtection() async throws {
        if deviceOwnerAuthAvailable {
            _ = try await authenticateUser(reason: "Vypněte ochranu aplikace na tomto zařízení.")
        }
        localProtectionEnabled = false
        lockState = deviceOwnerAuthAvailable ? .unlocked : .unavailable
        lastErrorMessage = nil
    }

    func unlockIfNeeded() async {
        guard localProtectionEnabled, deviceOwnerAuthAvailable else {
            lockState = deviceOwnerAuthAvailable ? .unlocked : .unavailable
            return
        }
        guard lockState != .unlocking else { return }

        do {
            _ = try await authenticateUser(reason: "Odemkněte aplikaci Správa vozidel.")
            lockState = .unlocked
            lastErrorMessage = nil
        } catch {
            lockState = .locked
            lastErrorMessage = error.localizedDescription
        }
    }

    func lockNow(isAuthenticated: Bool) {
        guard isAuthenticated, localProtectionEnabled, deviceOwnerAuthAvailable else { return }
        lastBackgroundAt = Date()
        lockState = .locked
    }

    private func authenticateUser(reason: String) async throws -> Bool {
        lockState = .unlocking
        let context = LAContext()
        context.localizedCancelTitle = "Zrušit"
        let policy: LAPolicy = .deviceOwnerAuthentication

        return try await withCheckedThrowingContinuation { continuation in
            var error: NSError?
            guard context.canEvaluatePolicy(policy, error: &error) else {
                if let error {
                    continuation.resume(throwing: APIError.serverError(Self.mapAuthenticationError(error)))
                } else {
                    continuation.resume(throwing: APIError.serverError("Ověření zařízení není dostupné."))
                }
                return
            }

            context.evaluatePolicy(policy, localizedReason: reason) { success, evalError in
                Task { @MainActor in
                    if let evalError {
                        continuation.resume(throwing: APIError.serverError(Self.mapAuthenticationError(evalError)))
                    } else {
                        continuation.resume(returning: success)
                    }
                }
            }
        }
    }

    private static func mapAuthenticationError(_ error: Error) -> String {
        let nsError = error as NSError
        switch nsError.code {
        case LAError.userCancel.rawValue, LAError.appCancel.rawValue, LAError.systemCancel.rawValue:
            return "Ověření bylo zrušeno."
        case LAError.biometryLockout.rawValue:
            return "Biometrie je dočasně zablokovaná. Použijte kód zařízení."
        case LAError.biometryNotAvailable.rawValue:
            return "Biometrie na zařízení není dostupná."
        case LAError.biometryNotEnrolled.rawValue:
            return "Na zařízení není nastavené Face ID / Touch ID."
        case LAError.passcodeNotSet.rawValue:
            return "Na zařízení není nastavený kód. Bez něj nelze ochranu aplikace zapnout."
        default:
            return "Ověření zařízení se nepodařilo."
        }
    }
}
