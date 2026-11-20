// TypeScript 6 richiede una dichiarazione esplicita per gli import di file
// non-TypeScript (allowArbitraryExtensions): global.css è il foglio Tailwind
// trasformato da NativeWind in fase di build.
declare const stylesheet: string;
export default stylesheet;
