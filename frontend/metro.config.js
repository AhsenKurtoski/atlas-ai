const { getDefaultConfig } = require('expo/metro-config');
const { withNativeWind } = require('nativewind/metro');

const config = getDefaultConfig(__dirname);

// NativeWind 4 compila `global.css` in stili nativi (iOS/Android) e in un
// foglio CSS per il web, così le schermate restano identiche su ogni piattaforma.
module.exports = withNativeWind(config, { input: './global.css' });
