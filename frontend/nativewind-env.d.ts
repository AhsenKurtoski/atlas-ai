/// <reference types="nativewind/types" />

declare module "*.png";
declare module "*.jpg";
declare module "*.jpeg";
declare module "*.gif";
declare module "*.svg";

// Shims per dipendenze installate via `npm install` ma non ancora presenti
// nell'ambiente di typecheck locale (consentono di validare tutto il resto).
declare module "@react-native-async-storage/async-storage" {
  export type AsyncStorageStatic = {
    getItem: (key: string) => Promise<string | null>;
    setItem: (key: string, value: string) => Promise<void>;
    removeItem: (key: string) => Promise<void>;
    clear: () => Promise<void>;
    multiGet: (keys: string[]) => Promise<[string, string | null][]>;
    multiSet: (kv: [string, string][]) => Promise<void>;
    multiRemove: (keys: string[]) => Promise<void>;
  };
  const AsyncStorage: AsyncStorageStatic;
  export default AsyncStorage;
}

// Fallback se nativewind/types non sono disponibili:
// estendiamo manualmente le props dei componenti React Native
// più comuni per includere `className` (usato da NativeWind/Tailwind).
import "react-native";

declare module "react-native" {
  interface TextProps {
    className?: string;
  }
  interface ViewProps {
    className?: string;
  }
  interface ImageProps {
    className?: string;
  }
  interface ScrollViewProps {
    className?: string;
  }
  interface TextInputProps {
    className?: string;
  }
  interface PressableProps {
    className?: string;
  }
  interface TouchableOpacityProps {
    className?: string;
  }
  interface TouchableHighlightProps {
    className?: string;
  }
  interface TouchableWithoutFeedbackProps {
    className?: string;
  }
  interface SafeAreaViewProps {
    className?: string;
  }
  interface KeyboardAvoidingViewProps {
    className?: string;
  }
  interface FlatListProps<ItemT> {
    className?: string;
  }
}
