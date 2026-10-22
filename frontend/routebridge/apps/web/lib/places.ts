/** Countries and Nigerian states for the sign-up form. Countries are ISO codes, named in the visitor's language by the browser. */

// Nigeria first, then its neighbours and other African countries RouteBridge is likely to meet, then everywhere else.
const FIRST = ['NG', 'GH', 'BJ', 'CM', 'NE', 'TD', 'TG', 'CI', 'SN', 'KE', 'ZA', 'EG'];
const ALL = ('AD AE AF AG AI AL AM AO AR AT AU AW AZ BA BB BD BE BF BG BH BI BJ BM BN BO BR BS BT BW BY BZ CA CD CF CG CH CI CL CM CN CO CR CU CV ' +
  'CY CZ DE DJ DK DM DO DZ EC EE EG ER ES ET FI FJ FM FR GA GB GD GE GH GM GN GQ GR GT GW GY HK HN HR HT HU ID IE IL IN IQ IR IS IT JM JO JP KE ' +
  'KG KH KI KM KN KR KW KZ LA LB LC LI LK LR LS LT LU LV LY MA MC MD ME MG MK ML MM MN MO MR MT MU MV MW MX MY MZ NA NE NG NI NL NO NP NR NZ OM ' +
  'PA PE PG PH PK PL PS PT PW PY QA RO RS RU RW SA SB SC SD SE SG SI SK SL SM SN SO SR SS ST SV SY SZ TD TG TH TJ TL TM TN TO TR TT TV TW TZ UA ' +
  'UG US UY UZ VA VC VE VN VU WS YE ZA ZM ZW').split(' ');

export function countryName(code: string, locale = 'en'): string {
  try { return new Intl.DisplayNames([locale], { type: 'region' }).of(code) ?? code; } catch { return code; }
}

export function countryOptions(locale = 'en'): { code: string; name: string }[] {
  const named = (codes: string[]) => codes.map((code) => ({ code, name: countryName(code, locale) }));
  const rest = named(ALL.filter((code) => !FIRST.includes(code))).sort((a, b) => a.name.localeCompare(b.name));
  return [...named(FIRST), ...rest];
}

export const NIGERIA_STATES = [
  'Abia', 'Adamawa', 'Akwa Ibom', 'Anambra', 'Bauchi', 'Bayelsa', 'Benue', 'Borno', 'Cross River', 'Delta', 'Ebonyi', 'Edo', 'Ekiti', 'Enugu',
  'Abuja (FCT)', 'Gombe', 'Imo', 'Jigawa', 'Kaduna', 'Kano', 'Katsina', 'Kebbi', 'Kogi', 'Kwara', 'Lagos', 'Nasarawa', 'Niger', 'Ogun', 'Ondo',
  'Osun', 'Oyo', 'Plateau', 'Rivers', 'Sokoto', 'Taraba', 'Yobe', 'Zamfara',
].sort((a, b) => a.localeCompare(b));
