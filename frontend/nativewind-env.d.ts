/// <reference types="nativewind/types" />

declare module "*.png";
declare module "*.jpg";
declare module "*.jpeg";
declare module "*.gif";
declare module "*.svg";

// Estende le props dei componenti React Native più comuni per includere
// `className` (usato da NativeWind/Tailwind).
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
