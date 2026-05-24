import Foundation

struct ServiceCategoryOption: Identifiable, Codable, Equatable {
    let id: String
    let label: String
    let icon: String

    static let defaultOptions: [ServiceCategoryOption] = [
        .init(id: "OLEJ", label: "Olej", icon: "🛢️"),
        .init(id: "BRZDY", label: "Brzdy", icon: "🛑"),
        .init(id: "PNEU", label: "Pneumatiky", icon: "⭕"),
        .init(id: "STK", label: "STK", icon: "✅"),
        .init(id: "DIAGNOSTIKA", label: "Diagnostika", icon: "🔧"),
        .init(id: "FILTRY", label: "Filtry", icon: "🔍"),
        .init(id: "CHLADICI", label: "Chladicí systém", icon: "❄️"),
        .init(id: "VYFUK", label: "Výfuk", icon: "💨"),
        .init(id: "OSVETLENI", label: "Osvětlení", icon: "💡"),
        .init(id: "KAROSERIE", label: "Karoserie", icon: "🚗"),
        .init(id: "INTERIER", label: "Interiér", icon: "🪑"),
        .init(id: "ELEKTRIKA", label: "Elektrika", icon: "⚡"),
        .init(id: "KLIMATIZACE", label: "Klimatizace", icon: "🌡️"),
        .init(id: "PREVENTIVNI", label: "Preventivní", icon: "🛡️"),
        .init(id: "OPRAVA", label: "Oprava", icon: "🔨"),
        .init(id: "JINE", label: "Jiné", icon: "📋"),
    ]

    static func merged(with custom: [ServiceCategoryOption]) -> [ServiceCategoryOption] {
        var seen = Set<String>()
        return (defaultOptions + custom).filter { option in
            guard !seen.contains(option.id) else { return false }
            seen.insert(option.id)
            return true
        }
    }
}

struct DocumentSourceOption: Identifiable, Codable, Equatable {
    let id: String
    let label: String

    static let defaultOptions: [DocumentSourceOption] = [
        .init(id: "invoice", label: "Faktura"),
        .init(id: "delivery_note", label: "Dodací list"),
        .init(id: "work_order", label: "Zakázkový list"),
        .init(id: "receipt", label: "Účtenka"),
        .init(id: "manual", label: "Ruční zápis"),
    ]
}

enum RecordEntryMode: String, Identifiable, CaseIterable, Codable {
    case manual
    case scan
    case template

    var id: String { rawValue }

    var iconName: String {
        switch self {
        case .manual:
            return "square.and.pencil"
        case .scan:
            return "doc.viewfinder"
        case .template:
            return "square.stack.3d.up"
        }
    }
}

struct ServiceRecordTemplate: Identifiable, Codable, Equatable {
    let id: UUID
    var name: String
    var icon: String
    var category: String
    var templateDescription: String?
    var note: String?
    var sourceType: String
    var description: String?
    var serviceSummary: String?
    var issueDescription: String?
    var currency: String
    var hasNextServiceDueDate: Bool
    var items: [ServiceRecordTemplateItem]

    static let presets: [ServiceRecordTemplate] = [
        ServiceRecordTemplate(
            id: UUID(uuidString: "B7F1D4D2-657D-4D6B-A8E9-7D9A2A7B4F01") ?? UUID(),
            name: "Pravidelný servis",
            icon: "🛠️",
            category: "PREVENTIVNI",
            templateDescription: "Olej, filtry a základní kontrola vozu",
            note: "Zkontrolovat provozní kapaliny a servisní interval.",
            sourceType: "invoice",
            description: "Pravidelný servis vozidla",
            serviceSummary: "Výměna oleje, filtrů a základní servisní kontrola",
            issueDescription: nil,
            currency: "CZK",
            hasNextServiceDueDate: true,
            items: [
                .init(name: "Motorový olej", quantity: "1", unit: "set", unitPrice: "", totalPrice: ""),
                .init(name: "Olejový filtr", quantity: "1", unit: "ks", unitPrice: "", totalPrice: ""),
            ]
        ),
        ServiceRecordTemplate(
            id: UUID(uuidString: "D276F897-0F8B-4A32-8AC5-05F32A0C5A41") ?? UUID(),
            name: "Pneuservis",
            icon: "🛞",
            category: "PNEU",
            templateDescription: "Přezutí, vyvážení a kontrola pneu",
            note: "Dopsat vzorek a tlak po přezutí.",
            sourceType: "invoice",
            description: "Pneuservis",
            serviceSummary: "Přezutí kol, vyvážení a kontrola stavu pneumatik",
            issueDescription: nil,
            currency: "CZK",
            hasNextServiceDueDate: false,
            items: [
                .init(name: "Přezutí kol", quantity: "1", unit: "úkon", unitPrice: "", totalPrice: ""),
                .init(name: "Vyvážení", quantity: "4", unit: "ks", unitPrice: "", totalPrice: ""),
            ]
        ),
        ServiceRecordTemplate(
            id: UUID(uuidString: "F3F544E8-25D8-4BFC-8D2E-A54D4D580E15") ?? UUID(),
            name: "Brzdy",
            icon: "🧰",
            category: "BRZDY",
            templateDescription: "Kotouče, destičky a kontrola brzdové soustavy",
            note: "Doplnit tloušťku destiček a test po opravě.",
            sourceType: "invoice",
            description: "Servis brzdové soustavy",
            serviceSummary: "Kontrola brzd, výměna destiček nebo kotoučů",
            issueDescription: "Vibrace při brzdění nebo opotřebené destičky",
            currency: "CZK",
            hasNextServiceDueDate: false,
            items: [
                .init(name: "Brzdové destičky", quantity: "1", unit: "sada", unitPrice: "", totalPrice: ""),
                .init(name: "Práce na brzdách", quantity: "1", unit: "úkon", unitPrice: "", totalPrice: ""),
            ]
        ),
    ]
}

struct ServiceRecordTemplateItem: Codable, Equatable {
    var name: String
    var quantity: String
    var unit: String
    var unitPrice: String
    var totalPrice: String

    init(name: String, quantity: String, unit: String, unitPrice: String, totalPrice: String) {
        self.name = name
        self.quantity = quantity
        self.unit = unit
        self.unitPrice = unitPrice
        self.totalPrice = totalPrice
    }
}
