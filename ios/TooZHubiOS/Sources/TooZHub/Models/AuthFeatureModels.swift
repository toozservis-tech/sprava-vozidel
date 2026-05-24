import Foundation

struct UserRegisterRequest: Encodable {
    let email: String
    let password: String
    let name: String?
    let ico: String?
    let dic: String?
    let street: String?
    let streetNumber: String?
    let city: String?
    let zip: String?
    let phone: String?
}

struct ServiceRegistrationRequest: Encodable {
    let email: String
    let password: String
    let ico: String
    let serviceName: String
    let responsiblePerson: String
    let phone: String
    let street: String
    let streetNumber: String?
    let city: String
    let zip: String
    let dic: String?
    let registrationPurpose: String
}

struct ServiceRegistrationResponse: Decodable {
    let requestId: Int
    let status: String
    let message: String
}

struct ForgotPasswordRequest: Encodable {
    let email: String
}

struct ForgotPasswordResponse: Decodable {
    let message: String?
    let emailSent: Bool?
    let resetUrl: String?
    let error: String?
    let errorDetail: String?
}

struct AresPublicResponse: Decodable {
    struct Sidlo: Decodable {
        let nazevUlice: String?
        let cisloDomovni: Int?
        let cisloOrientacni: Int?
        let cisloOrientacniPismeno: String?
        let nazevObce: String?
        let psc: String?

        enum CodingKeys: String, CodingKey {
            case nazevUlice
            case cisloDomovni
            case cisloOrientacni
            case cisloOrientacniPismeno
            case nazevObce
            case psc
        }

        init(from decoder: Decoder) throws {
            let container = try decoder.container(keyedBy: CodingKeys.self)
            nazevUlice = try container.decodeIfPresent(String.self, forKey: .nazevUlice)
            cisloDomovni = try container.decodeIfPresent(Int.self, forKey: .cisloDomovni)
            cisloOrientacni = try container.decodeIfPresent(Int.self, forKey: .cisloOrientacni)
            cisloOrientacniPismeno = try container.decodeIfPresent(String.self, forKey: .cisloOrientacniPismeno)
            nazevObce = try container.decodeIfPresent(String.self, forKey: .nazevObce)
            psc = container.decodeFlexibleString(forKey: .psc)
        }
    }

    let ico: String?
    let companyName: String?
    let obchodniJmeno: String?
    let nazev: String?
    let dic: String?
    let street: String?
    let houseNumber: String?
    let city: String?
    let zip: String?
    let sidlo: Sidlo?

    enum CodingKeys: String, CodingKey {
        case ico
        case companyName
        case obchodniJmeno
        case nazev
        case dic
        case street
        case houseNumber
        case city
        case zip
        case sidlo
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        ico = container.decodeFlexibleString(forKey: .ico)
        companyName = try container.decodeIfPresent(String.self, forKey: .companyName)
        obchodniJmeno = try container.decodeIfPresent(String.self, forKey: .obchodniJmeno)
        nazev = try container.decodeIfPresent(String.self, forKey: .nazev)
        dic = try container.decodeIfPresent(String.self, forKey: .dic)
        street = try container.decodeIfPresent(String.self, forKey: .street)
        houseNumber = container.decodeFlexibleString(forKey: .houseNumber)
        city = try container.decodeIfPresent(String.self, forKey: .city)
        zip = container.decodeFlexibleString(forKey: .zip)
        sidlo = try container.decodeIfPresent(Sidlo.self, forKey: .sidlo)
    }

    var resolvedCompanyName: String? {
        companyName ?? obchodniJmeno ?? nazev
    }

    var resolvedStreet: String? {
        street ?? sidlo?.nazevUlice
    }

    var resolvedStreetNumber: String? {
        if let houseNumber, !houseNumber.isEmpty {
            return houseNumber
        }
        var parts: [String] = []
        if let domovni = sidlo?.cisloDomovni {
            parts.append(String(domovni))
        }
        if let orientacni = sidlo?.cisloOrientacni {
            parts.append(String(orientacni))
        }
        if let pismeno = sidlo?.cisloOrientacniPismeno, !pismeno.isEmpty {
            parts.append(pismeno)
        }
        return parts.isEmpty ? nil : parts.joined(separator: "/")
    }

    var resolvedCity: String? {
        city ?? sidlo?.nazevObce
    }

    var resolvedZip: String? {
        zip ?? sidlo?.psc
    }
}

private extension KeyedDecodingContainer {
    func decodeFlexibleString(forKey key: K) -> String? {
        if let value = try? decodeIfPresent(String.self, forKey: key) {
            return value
        }
        if let intValue = try? decodeIfPresent(Int.self, forKey: key) {
            return String(intValue)
        }
        if let doubleValue = try? decodeIfPresent(Double.self, forKey: key) {
            return String(Int(doubleValue))
        }
        return nil
    }
}

struct VinLookupResponse: Decodable {
    let vin: String
    let make: String?
    let model: String?
    let year: Int?
    let engine: String?
    let source: String
    let detail: String?
}

struct DecoderResponse: Decodable {
    let success: Bool
    let data: DecoderVehicleData?
    let errors: [String]
}

struct DecoderVehicleData: Decodable {
    let vin: String?
    let plate: String?
    let make: String?
    let model: String?
    let modelYear: Int?
    let productionYear: Int?
    let engineCode: String?
    let engineDisplacementCc: Int?
    let enginePowerKw: Int?
    let fuelType: String?
    let stkValidUntil: String?
    let techInspectionValidTo: String?
}
