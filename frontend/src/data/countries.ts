import type { Country } from '../domain/countries';

let request: Promise<Country[]> | undefined;
export function loadCountries(): Promise<Country[]> {
  if (!request) {
    request = fetch(`${import.meta.env.BASE_URL}geography/countries.json`)
      .then(response => { if (!response.ok) throw new Error('Country data unavailable'); return response.json() as Promise<Country[]>; })
      .catch(error => { request = undefined; throw error; });
  }
  return request;
}
