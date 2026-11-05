import {defineConfig} from 'sanity'
import {structureTool} from 'sanity/structure'
import {schemaTypes} from './schemaTypes'
import project from './project.json'

export default defineConfig({
  name: 'default',
  title: 'Psychologie im NS – Archiv',
  projectId: project.projectId,
  dataset: project.dataset,
  plugins: [
    structureTool({
      structure: (S) =>
        S.list()
          .title('Archiv')
          .items([
            S.documentTypeListItem('person').title('Personen'),
            S.documentTypeListItem('ort').title('Orte'),
            S.documentTypeListItem('artikel').title('Artikel'),
          ]),
    }),
  ],
  schema: {types: schemaTypes},
})
