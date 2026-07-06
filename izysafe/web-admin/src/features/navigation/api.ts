import { apiGet } from "@/lib/api";

/** A navigation item the current admin may see (already role/visibility filtered). */
export interface MenuNavItem {
  item_key: string;
  label_key: string;
  icon: string | null;
  path: string;
}

/** The dynamic sidebar for the logged-in admin (GET /schools/menu). */
export function fetchMenu(): Promise<MenuNavItem[]> {
  return apiGet<MenuNavItem[]>("/schools/menu");
}
