module.exports = function (api) {
  api.cache(true);
  return {
    presets: [
      // jsxImportSource abilita il runtime NativeWind 4 sui componenti.
      ['babel-preset-expo', { jsxImportSource: 'nativewind' }],
      'nativewind/babel',
    ],
  };
};
