import SwiftUI

struct RootView: View {
    @EnvironmentObject private var env: AppEnvironment
    @EnvironmentObject private var authManager: AuthManager

    var body: some View {
        Group {
            if authManager.isAuthenticated {
                MainTabView()
            } else {
                LoginView()
            }
        }
        .animation(.easeInOut(duration: 0.25), value: authManager.isAuthenticated)
        .safeAreaInset(edge: .top, spacing: 0) {
            if env.serverStatusMonitor.state != .online {
                HStack {
                    Spacer()
                    ServerStatusBadge(state: env.serverStatusMonitor.state)
                        .onTapGesture {
                            Task { await env.serverStatusMonitor.checkNow() }
                        }
                }
                .padding(.horizontal, 12)
                .padding(.top, authManager.isAuthenticated ? 2 : 6)
                .padding(.bottom, authManager.isAuthenticated ? 6 : 2)
            }
        }
        .overlay(alignment: .bottom) {
            if let message = env.serverStatusMonitor.userMessage {
                HStack(alignment: .top, spacing: 10) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .foregroundStyle(.yellow)
                    Text(message)
                        .font(.caption)
                        .foregroundStyle(.white)
                        .multilineTextAlignment(.leading)
                    Spacer()
                    Button("OK") {
                        env.serverStatusMonitor.stop()
                        env.serverStatusMonitor.start()
                    }
                    .font(.caption.bold())
                    .foregroundStyle(.white)
                }
                .padding(12)
                .background(.black.opacity(0.82), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                .padding(.horizontal, 12)
                .padding(.bottom, 16)
            }
        }
        .overlay {
            if authManager.isAuthenticated && env.appLockManager.isLocked {
                AppLockOverlay(
                    title: env.appLockManager.localizedProtectionName,
                    deviceSummary: env.appLockManager.deviceProtectionSummary,
                    errorMessage: env.appLockManager.lastErrorMessage
                ) {
                    Task { await env.appLockManager.unlockIfNeeded() }
                }
            }
        }
        .onAppear {
            env.appLockManager.updateScenePhase(.active, isAuthenticated: authManager.isAuthenticated)
        }
        .onChange(of: authManager.isAuthenticated) { _, isAuthenticated in
            env.appLockManager.updateScenePhase(.active, isAuthenticated: isAuthenticated)
        }
    }
}

private struct AppLockOverlay: View {
    let title: String
    let deviceSummary: String
    let errorMessage: String?
    let onUnlock: () -> Void

    var body: some View {
        ZStack {
            Theme.Colors.background.opacity(0.94)
                .ignoresSafeArea()

            VStack(spacing: Theme.Spacing.lg) {
                Image(systemName: "lock.shield.fill")
                    .font(.system(size: 34, weight: .semibold))
                    .foregroundStyle(Theme.Colors.warning)
                    .frame(width: 72, height: 72)
                    .background(Theme.Colors.warning.opacity(0.16), in: RoundedRectangle(cornerRadius: Theme.Radius.xl, style: .continuous))

                VStack(spacing: Theme.Spacing.xs) {
                    Text("Aplikace je zamčená")
                        .font(Theme.Typography.sectionTitle)
                        .foregroundStyle(.white)
                    Text("Pro pokračování použijte \(title) nebo kód zařízení.")
                        .font(Theme.Typography.body)
                        .foregroundStyle(Theme.Colors.textSecondary)
                        .multilineTextAlignment(.center)
                    Text(deviceSummary)
                        .font(Theme.Typography.caption)
                        .foregroundStyle(Theme.Colors.textSecondary)
                        .multilineTextAlignment(.center)
                }

                if let errorMessage, !errorMessage.isEmpty {
                    Text(errorMessage)
                        .font(Theme.Typography.captionStrong)
                        .foregroundStyle(Theme.Colors.warning)
                        .multilineTextAlignment(.center)
                }

                Button("Odemknout aplikaci", action: onUnlock)
                    .buttonStyle(PrimaryActionButtonStyle())
            }
            .padding(Theme.Spacing.lg)
            .frame(maxWidth: 420)
            .hubDarkCard()
            .padding(.horizontal, Theme.Spacing.md)
        }
        .transition(.opacity)
    }
}
