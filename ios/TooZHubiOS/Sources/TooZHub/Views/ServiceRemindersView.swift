import SwiftUI

struct ServiceRemindersView: View {
    @EnvironmentObject private var env: AppEnvironment
    @StateObject private var viewModel: ServiceRemindersViewModel
    @State private var showAddSheet = false
    @State private var editingReminder: ServiceWorkspaceReminder?

    init() {
        _viewModel = StateObject(wrappedValue: ServiceRemindersViewModel(service: ServiceWorkspaceService(api: APIClient())))
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: Theme.Spacing.lg) {
                    SectionHeader(
                        title: "Servisní připomínky",
                        subtitle: "Úkoly klientů ve workspace",
                        trailing: AnyView(PillBadge(title: "\(viewModel.reminders.count)", style: .success))
                    )

                    if viewModel.isLoading {
                        ProgressView()
                            .tint(.white)
                            .frame(maxWidth: .infinity)
                            .padding(.top, 60)
                    } else if viewModel.loadState == .backendUnavailable {
                        EmptyStateView(
                            icon: "clock.badge.exclamationmark",
                            title: "Servisní připomínky čekají na nasazení",
                            subtitle: "Workspace routy pro připomínky a klienty zatím na tomto serveru nejsou k dispozici."
                        ) {
                            Task { await reload() }
                        }
                    } else if let error = viewModel.error {
                        ErrorStateView(message: error) { Task { await reload() } }
                    } else if viewModel.reminders.isEmpty {
                        EmptyStateView(
                            icon: "clock.badge.checkmark",
                            title: "Bez připomínek",
                            subtitle: "Servisní workspace momentálně neobsahuje aktivní připomínky.",
                            actionTitle: "Přidat připomínku"
                        ) {
                            showAddSheet = true
                        }
                    } else {
                        ForEach(viewModel.reminders) { item in
                            VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
                                Text(item.text)
                                    .font(Theme.Typography.headline)
                                    .foregroundStyle(.white)

                                Text("Klient: \(item.customerName ?? "#\(item.customerId)") • Typ: \(item.type)")
                                    .font(Theme.Typography.caption)
                                    .foregroundStyle(Theme.Colors.textSecondary)

                                if let due = item.dueDate {
                                    Text("Termín: \(due)")
                                        .font(Theme.Typography.caption)
                                        .foregroundStyle(Theme.Colors.textSecondary)
                                }

                                HStack(spacing: Theme.Spacing.sm) {
                                    Button("Upravit") {
                                        editingReminder = item
                                    }
                                    .buttonStyle(InlineChipButtonStyle(isSelected: true))

                                    Button(item.isCompleted ? "Označit aktivní" : "Dokončit") {
                                        guard let token = env.authManager.token else { return }
                                        Task {
                                            await viewModel.updateReminder(
                                                reminderId: item.id,
                                                request: ServiceWorkspaceReminderUpdateRequest(
                                                    type: nil,
                                                    text: nil,
                                                    dueDate: nil,
                                                    notifyAt: nil,
                                                    notificationMethod: nil,
                                                    isCompleted: !item.isCompleted
                                                ),
                                                token: token
                                            )
                                        }
                                    }
                                    .buttonStyle(InlineChipButtonStyle(isSelected: item.isCompleted))

                                    Button("Smazat") {
                                        guard let token = env.authManager.token else { return }
                                        Task { await viewModel.deleteReminder(reminderId: item.id, token: token) }
                                    }
                                    .buttonStyle(InlineChipButtonStyle(isSelected: false))
                                }
                            }
                            .hubDarkCard()
                        }
                    }
                }
                .padding(Theme.Spacing.md)
                .padding(.bottom, Theme.Spacing.xxl + 18)
            }
            .hubPageBackground()
            .navigationTitle("Připomínky")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarColorScheme(.dark, for: .navigationBar)
            .toolbarBackground(.hidden, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        showAddSheet = true
                    } label: {
                        Image(systemName: "plus")
                            .font(.headline.bold())
                            .foregroundStyle(Theme.Colors.textOnLight)
                            .frame(width: 34, height: 34)
                            .background(Theme.Colors.primary, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                    }
                }
            }
            .sheet(isPresented: $showAddSheet) {
                ServiceWorkspaceReminderSheet(
                    customers: viewModel.customers,
                    vehicles: viewModel.selectedCustomerVehicles,
                    initial: nil
                ) { request in
                    guard let token = env.authManager.token else { return }
                    Task {
                        await viewModel.createReminder(request, token: token)
                    }
                } onCustomerChanged: { customerId in
                    guard let token = env.authManager.token else { return }
                    Task { await viewModel.loadVehiclesForCustomer(customerId: customerId, token: token) }
                }
            }
            .sheet(item: $editingReminder) { reminder in
                ServiceWorkspaceReminderSheet(
                    customers: viewModel.customers,
                    vehicles: viewModel.selectedCustomerVehicles,
                    initial: reminder
                ) { request in
                    guard let token = env.authManager.token else { return }
                    Task {
                        await viewModel.updateReminder(
                            reminderId: reminder.id,
                            request: ServiceWorkspaceReminderUpdateRequest(
                                type: request.type,
                                text: request.text,
                                dueDate: request.dueDate,
                                notifyAt: request.notifyAt,
                                notificationMethod: request.notificationMethod,
                                isCompleted: nil
                            ),
                            token: token
                        )
                    }
                } onCustomerChanged: { customerId in
                    guard let token = env.authManager.token else { return }
                    Task { await viewModel.loadVehiclesForCustomer(customerId: customerId, token: token) }
                }
            }
            .task { await reload() }
            .refreshable { await reload() }
        }
    }

    private func reload() async {
        guard let token = env.authManager.token else { return }
        await viewModel.load(token: token)
        if let first = viewModel.customers.first?.customerId {
            await viewModel.loadVehiclesForCustomer(customerId: first, token: token)
        }
    }
}

private struct ServiceWorkspaceReminderSheet: View {
    let customers: [ServiceWorkspaceCustomer]
    let vehicles: [ServiceWorkspaceVehicle]
    let initial: ServiceWorkspaceReminder?
    let onSubmit: (ServiceWorkspaceReminderCreateRequest) -> Void
    let onCustomerChanged: (Int) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var customerId: Int = 0
    @State private var vehicleId: Int = 0
    @State private var text = ""
    @State private var type = "SERVIS"
    @State private var dueDate = Date().addingTimeInterval(7 * 24 * 3600)
    @State private var notificationMethod = "both"

    var body: some View {
        NavigationStack {
            Form {
                Section("Klient") {
                    Picker("Zákazník", selection: $customerId) {
                        ForEach(customers) { customer in
                            Text(customer.name ?? customer.email).tag(customer.customerId)
                        }
                    }
                    .onChange(of: customerId) { _, value in
                        onCustomerChanged(value)
                    }

                    Picker("Vozidlo", selection: $vehicleId) {
                        Text("Bez vozidla").tag(0)
                        ForEach(vehicles) { vehicle in
                            Text(vehicle.displayName).tag(vehicle.id)
                        }
                    }
                }

                Section("Připomínka") {
                    TextField("Text připomínky", text: $text)
                    TextField("Typ", text: $type)
                    DatePicker("Termín", selection: $dueDate, displayedComponents: .date)
                    Picker("Notifikace", selection: $notificationMethod) {
                        Text("Aplikace").tag("app")
                        Text("Email").tag("email")
                        Text("Oboje").tag("both")
                    }
                }
            }
            .navigationTitle(initial == nil ? "Nová připomínka" : "Upravit připomínku")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Zrušit") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Uložit") {
                        let formatter = DateFormatter()
                        formatter.locale = Locale(identifier: "en_US_POSIX")
                        formatter.timeZone = TimeZone(secondsFromGMT: 0)
                        formatter.dateFormat = "yyyy-MM-dd"
                        onSubmit(
                            ServiceWorkspaceReminderCreateRequest(
                                customerId: customerId,
                                vehicleId: vehicleId == 0 ? nil : vehicleId,
                                type: type,
                                text: text,
                                dueDate: formatter.string(from: dueDate),
                                notifyAt: nil,
                                notificationMethod: notificationMethod
                            )
                        )
                        dismiss()
                    }
                    .disabled(customerId == 0 || text.trimmingCharacters(in: .whitespacesAndNewlines).count < 3)
                }
            }
            .onAppear {
                if let initial {
                    customerId = initial.customerId
                    text = initial.text
                    type = initial.type
                    notificationMethod = "both"
                    vehicleId = initial.vehicleId ?? 0
                } else {
                    customerId = customers.first?.customerId ?? 0
                    vehicleId = 0
                }
                if customerId != 0 {
                    onCustomerChanged(customerId)
                }
            }
        }
    }
}
