import SwiftUI

@main
struct SpravaVozidelApp: App {
    @StateObject private var environment = AppEnvironment()
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(environment)
                .environmentObject(environment.authManager)
                .environmentObject(environment.dashboardViewModel)
                .environmentObject(environment.vehiclesViewModel)
                .environmentObject(environment.reservationsViewModel)
                .environmentObject(environment.serviceViewModel)
                .environmentObject(environment.accountViewModel)
                .task {
                    await environment.authManager.bootstrap()
                }
                .onChange(of: scenePhase) { _, newPhase in
                    environment.appLockManager.updateScenePhase(newPhase, isAuthenticated: environment.authManager.isAuthenticated)
                }
        }
    }
}
