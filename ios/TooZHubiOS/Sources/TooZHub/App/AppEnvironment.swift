import Foundation
import Combine
import os.log

@MainActor
final class AppEnvironment: ObservableObject {
    let apiClient = APIClient()
    let dashboardService: DashboardService
    let vehicleService: VehicleService
    let reservationService: ReservationService
    let accountService: AccountService
    let userFeatureService: UserFeatureService
    let deviceCapabilityService = DeviceCapabilityService()
    let appLockManager = AppLockManager()
    let serverStatusMonitor = ServerStatusMonitor()
    let recordConfigurationStore = RecordConfigurationStore()
    let authManager: AuthManager
    let dashboardViewModel: DashboardViewModel
    let vehiclesViewModel: VehiclesViewModel
    let reservationsViewModel: ReservationsViewModel
    let serviceViewModel: ServiceViewModel
    let accountViewModel: AccountViewModel
    @Published var requestedUserTab: String?
    @Published var requestedServiceTab: String?
    private var cancellables: Set<AnyCancellable> = []

    init() {
        let configuredBaseURL = APIClient.configuredBaseURLString()
#if DEBUG
        print("[API] Configured base URL: \(configuredBaseURL)")
#endif
        dashboardService = DashboardService(api: apiClient)
        vehicleService = VehicleService(api: apiClient)
        reservationService = ReservationService(api: apiClient)
        accountService = AccountService(api: apiClient)
        userFeatureService = UserFeatureService(api: apiClient)
        authManager = AuthManager(api: apiClient)
        dashboardViewModel = DashboardViewModel(service: dashboardService)
        vehiclesViewModel = VehiclesViewModel(service: vehicleService, featureService: userFeatureService)
        reservationsViewModel = ReservationsViewModel(service: reservationService, featureService: userFeatureService)
        serviceViewModel = ServiceViewModel(api: apiClient, featureService: userFeatureService)
        accountViewModel = AccountViewModel(service: accountService, featureService: userFeatureService)

        authManager.objectWillChange
            .sink { [weak self] _ in
                self?.objectWillChange.send()
            }
            .store(in: &cancellables)

        appLockManager.objectWillChange
            .sink { [weak self] _ in
                self?.objectWillChange.send()
            }
            .store(in: &cancellables)

        serverStatusMonitor.objectWillChange
            .sink { [weak self] _ in
                self?.objectWillChange.send()
            }
            .store(in: &cancellables)

        serverStatusMonitor.start()
    }
}

@MainActor
final class ServerStatusMonitor: ObservableObject {
    enum State {
        case connecting
        case online
        case offline
    }

    @Published private(set) var state: State = .connecting
    @Published private(set) var userMessage: String?

    private var timer: Timer?
    private var isChecking = false
    private var initialStateResolved = false
    private var connectingFallbackTask: Task<Void, Never>?
    private var startupTask: Task<Void, Never>?
    private let logger = Logger(subsystem: Bundle.main.bundleIdentifier ?? "sprava-vozidel-ios", category: "ServerStatus")

    func start() {
        guard timer == nil else { return }
        state = .connecting
        initialStateResolved = false
        userMessage = nil
        scheduleTimer()
        scheduleConnectingFallback()
        logger.debug("Server status monitor started")
        startupTask?.cancel()
        startupTask = Task { [weak self] in
            try? await Task.sleep(nanoseconds: 400_000_000)
            guard let self else { return }
            await self.checkNow(showConnectingState: true)
        }
    }

    func stop() {
        timer?.invalidate()
        timer = nil
        startupTask?.cancel()
        startupTask = nil
        connectingFallbackTask?.cancel()
        connectingFallbackTask = nil
        logger.debug("Server status monitor stopped")
    }

    func checkNow(showConnectingState: Bool = false) async {
        guard !isChecking else { return }
        isChecking = true
        defer { isChecking = false }

        if showConnectingState || !initialStateResolved {
            state = .connecting
            logger.debug("Server status set to connecting")
        }

        let candidateURLs = healthCandidateURLs()
        logger.debug("Checking server reachability with \(candidateURLs.count) candidate URLs")
        guard !candidateURLs.isEmpty else {
            state = .offline
            userMessage = "Problém s nastavením serveru. Obraťte se na vývojáře aplikace nebo správce."
            initialStateResolved = true
            logger.error("No candidate health URLs available")
            return
        }

        let reachable = await Self.reachableWithTimeout(urls: candidateURLs, timeoutSeconds: 6)
        if reachable {
            state = .online
            userMessage = nil
            initialStateResolved = true
            connectingFallbackTask?.cancel()
            connectingFallbackTask = nil
            logger.debug("Server status resolved: online")
            return
        }

        state = .offline
        userMessage = "Server je offline nebo nedostupný. Obraťte se na vývojáře aplikace nebo správce."
        initialStateResolved = true
        connectingFallbackTask?.cancel()
        connectingFallbackTask = nil
        logger.error("Server status resolved: offline")
    }

    private func scheduleTimer() {
        timer = Timer.scheduledTimer(withTimeInterval: 15, repeats: true) { [weak self] _ in
            guard let self else { return }
            Task { await self.checkNow(showConnectingState: false) }
        }
    }

    private func scheduleConnectingFallback() {
        connectingFallbackTask?.cancel()
        connectingFallbackTask = Task { [weak self] in
            try? await Task.sleep(nanoseconds: 12_000_000_000)
            guard let self else { return }
            guard self.state == .connecting else { return }

            self.state = .offline
            if self.userMessage == nil {
                self.userMessage = "Kontrola serveru trvá příliš dlouho. Zkuste to prosím znovu."
            }
            self.initialStateResolved = true
            self.logger.error("Connecting watchdog fallback triggered -> offline")
        }
    }

    private func healthCandidateURLs() -> [URL] {
        let baseCandidates = [
            APIClient.configuredBaseURLString(),
            "https://hub.toozservis.cz"
        ]

        var urls: [URL] = []

        for rawBase in baseCandidates {
            guard let base = normalizedURL(from: rawBase) else { continue }

            let endpoints = ["health", "api/health", "api/v1/health"]
            for endpoint in endpoints {
                let full = base.appendingPathComponent(endpoint)
                if !urls.contains(where: { $0.absoluteString == full.absoluteString }) {
                    urls.append(full)
                }
            }
        }

        return Array(urls.prefix(3))
    }

    private func normalizedURL(from raw: String) -> URL? {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        if let direct = URL(string: trimmed), direct.scheme != nil {
            return direct
        }
        return URL(string: "https://\(trimmed)")
    }

    nonisolated private static func reachableWithTimeout(urls: [URL], timeoutSeconds: UInt64) async -> Bool {
        await withTaskGroup(of: Bool.self) { group in
            group.addTask {
                for url in urls {
                    if await isReachable(url: url) {
                        return true
                    }
                }
                return false
            }
            group.addTask {
                try? await Task.sleep(nanoseconds: timeoutSeconds * 1_000_000_000)
                return false
            }

            let result = await group.next() ?? false
            group.cancelAll()
            return result
        }
    }

    nonisolated private static func isReachable(url: URL) async -> Bool {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.waitsForConnectivity = false
        configuration.timeoutIntervalForRequest = 2
        configuration.timeoutIntervalForResource = 3
        configuration.requestCachePolicy = .reloadIgnoringLocalAndRemoteCacheData
        configuration.urlCache = nil
        configuration.httpShouldUsePipelining = false
        configuration.httpAdditionalHeaders = [
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Connection": "close"
        ]
        let session = URLSession(configuration: configuration)
        defer { session.invalidateAndCancel() }

        var request = URLRequest(url: url)
        request.httpMethod = "HEAD"
        request.timeoutInterval = 2
        request.cachePolicy = .reloadIgnoringLocalAndRemoteCacheData

        do {
            let (_, response) = try await session.data(for: request)
            guard let http = response as? HTTPURLResponse else { return false }

            // 4xx může znamenat, že endpoint je chráněn (např. Cloudflare), ale server běží.
            return (200...499).contains(http.statusCode)
        } catch {
            return false
        }
    }

    deinit {
        timer?.invalidate()
    }
}
