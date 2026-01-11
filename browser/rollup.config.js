import typescript from '@rollup/plugin-typescript';

export default {
  input: 'src/index.ts',
  output: [
    {
      file: 'dist/devlogs.cjs.js',
      format: 'cjs',
      sourcemap: true,
    },
    {
      file: 'dist/devlogs.esm.js',
      format: 'esm',
      sourcemap: true,
    },
    {
      file: 'dist/devlogs.iife.js',
      format: 'iife',
      name: 'devlogs',
      sourcemap: true,
    },
  ],
  plugins: [
    typescript({
      tsconfig: './tsconfig.json',
      declaration: true,
      declarationDir: 'dist',
    }),
  ],
};
