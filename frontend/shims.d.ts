declare module "*.png";
declare module "*.jpg";
declare module "*.jpeg";
declare module "*.gif";
declare module "*.svg";
declare module "*.webp";

declare module "@react-native-async-storage/async-storage" {
  type ErrorCallback = (error?: Error) => void;
  type ResultCallback<T> = (error?: Error, result?: T) => void;

  export interface AsyncStorageStatic {
    getItem: (key: string, callback?: ResultCallback<string | null>) => Promise<string | null>;
    setItem: (key: string, value: string, callback?: ErrorCallback) => Promise<void>;
    removeItem: (key: string, callback?: ErrorCallback) => Promise<void>;
    mergeItem: (key: string, value: string, callback?: ErrorCallback) => Promise<void>;
    clear: (callback?: ErrorCallback) => Promise<void>;
    getAllKeys: (callback?: ResultCallback<string[]>) => Promise<string[]>;
    multiGet: (keys: string[], callback?: ResultCallback<[string, string | null][]>) => Promise<[string, string | null][]>;
    multiSet: (kv: [string, string][], callback?: ResultCallback<[string, string][]>) => Promise<void>;
    multiRemove: (keys: string[], callback?: ErrorCallback) => Promise<void>;
    multiMerge: (kv: [string, string][], callback?: ErrorCallback) => Promise<void>;
    useAsyncStorage: (key: string) => {
      getItem: () => Promise<string | null>;
      setItem: (value: string) => Promise<void>;
      removeItem: () => Promise<void>;
      mergeItem: (value: string) => Promise<void>;
    };
  }

  const AsyncStorage: AsyncStorageStatic;
  export default AsyncStorage;
}
