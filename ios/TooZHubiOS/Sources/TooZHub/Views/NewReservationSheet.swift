import Foundation
import SwiftUI

struct NewReservationSheet: View {
    let vehicles: [ReservationVehicleOption]
    let services: [ServiceContact]
    let role: String
    let currentUserId: Int?
    let onCreate: (Int, Int, String, String, Date) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var vehicleId: Int = 0
    @State private var serviceId: Int = 0
    @State private var serviceType = "Pravidelný servis"
    @State private var note = ""
    @State private var date = Date().addingTimeInterval(86_400)

    var body: some View {
        NavigationStack {
            Form {
                Section("Vozidlo") {
                    if vehicles.isEmpty {
                        Text("Pro rezervaci zatím není dostupné žádné vozidlo.")
                            .font(Theme.Typography.caption)
                            .foregroundStyle(Theme.Colors.textOnLightSecondary)
                    } else {
                        Picker("Vyberte vozidlo", selection: $vehicleId) {
                            ForEach(vehicles) { vehicle in
                                Text(vehicleLabel(vehicle)).tag(vehicle.id)
                            }
                        }
                    }
                }

                Section("Servis") {
                    if services.isEmpty {
                        Text("Nebyl nalezen žádný servis. Zkontrolujte propojení účtu.")
                            .font(Theme.Typography.caption)
                            .foregroundStyle(Theme.Colors.textOnLightSecondary)
                    } else {
                        Picker("Vyberte servis", selection: $serviceId) {
                            ForEach(services) { service in
                                Text(serviceLabel(service)).tag(service.id)
                            }
                        }
                        .disabled(isServiceRole)
                    }
                }

                Section("Detaily") {
                    TextField("Typ služby", text: $serviceType)
                    DatePicker("Termín", selection: $date)
                    TextField("Poznámka", text: $note, axis: .vertical)
                        .lineLimit(3...5)
                }
            }
            .scrollContentBackground(.hidden)
            .background {
                Theme.Colors.pageGradient.ignoresSafeArea()
            }
            .navigationTitle("Nová rezervace")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Zavřít") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Uložit") {
                        onCreate(vehicleId, serviceId, serviceType, note, date)
                        dismiss()
                    }
                    .disabled(vehicleId == 0 || serviceId == 0 || vehicles.isEmpty || services.isEmpty)
                }
            }
            .toolbarBackground(.hidden, for: .navigationBar)
            .onAppear {
                vehicleId = vehicles.first?.id ?? 0
                if isServiceRole, let currentUserId, services.contains(where: { $0.id == currentUserId }) {
                    serviceId = currentUserId
                } else {
                    serviceId = services.first?.id ?? 0
                }
            }
        }
    }

    private var isServiceRole: Bool {
        role.lowercased() == "service"
    }

    private func vehicleLabel(_ vehicle: ReservationVehicleOption) -> String {
        if let plate = vehicle.plate, !plate.isEmpty {
            return "\(vehicle.name) (\(plate))"
        }
        return vehicle.name
    }

    private func serviceLabel(_ service: ServiceContact) -> String {
        var suffixParts: [String] = []
        if let city = service.city, !city.isEmpty {
            suffixParts.append(city)
        }
        if let distanceKm = service.distanceKm {
            suffixParts.append(String(format: "%.1f km", distanceKm))
        }
        if suffixParts.isEmpty {
            return service.name
        }
        return "\(service.name) · \(suffixParts.joined(separator: " · "))"
    }
}
