// Shared types for the storefront (hard case: type/implementation split).

export interface CartLine {
  sku: string;
  unitPrice: number;
  qty: number;
  note?: string;
}

export type LoyaltyTier = "bronze" | "silver" | "gold" | "none";

export interface TaxProfile {
  country: string;
  rate: number;
  includesVat: boolean;
}

export interface Quote {
  currency: string;
  formatted: string;
  subtotal: number;
  tax: number;
  shipping: number;
  loyalty: number;
  total: number;
}
