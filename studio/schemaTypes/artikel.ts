import {defineField, defineType} from 'sanity'
import {artikelSeiten} from './artikelSeiten'

export const artikel = defineType({
  name: 'artikel',
  title: 'Artikel',
  type: 'document',
  description: 'Verweis auf einen Artikel der Website, damit Personen und Orte darauf verlinken können.',
  fields: [
    defineField({name: 'titel', title: 'Titel', type: 'string', validation: (r) => r.required()}),
    defineField({name: 'autor', title: 'Autor:in', type: 'string'}),
    defineField({
      name: 'seite',
      title: 'Seite auf der Website',
      type: 'string',
      options: {list: artikelSeiten},
      description: 'Leer lassen, wenn der Artikel (noch) nicht online ist – dann erscheint der Titel ohne Link.',
    }),
  ],
  preview: {select: {title: 'titel', subtitle: 'autor'}},
})
