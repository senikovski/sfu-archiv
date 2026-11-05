import {defineField, defineType} from 'sanity'

export const ort = defineType({
  name: 'ort',
  title: 'Ort',
  type: 'document',
  fields: [
    defineField({name: 'name', title: 'Name', type: 'string', validation: (r) => r.required()}),
    defineField({name: 'adresse', title: 'Adresse', type: 'string'}),
    defineField({name: 'text', title: 'Text', type: 'text', rows: 5}),
    defineField({name: 'bild', title: 'Bild', type: 'image', options: {hotspot: true}}),
    defineField({
      name: 'lage',
      title: 'Lage auf der Karte',
      type: 'object',
      description:
        'Koordinaten in Dezimalgrad, z. B. Breite 48.2134, Länge 16.3576 (Universität Wien). Tipp: in Google Maps Rechtsklick auf den Ort → die Zahlen anklicken kopiert sie.',
      fields: [
        defineField({
          name: 'lat',
          title: 'Breite (lat)',
          type: 'number',
          validation: (r) => r.required().min(-90).max(90),
        }),
        defineField({
          name: 'lng',
          title: 'Länge (lng)',
          type: 'number',
          validation: (r) => r.required().min(-180).max(180),
        }),
      ],
      options: {columns: 2},
      validation: (r) => r.required(),
    }),
    defineField({
      name: 'artikel',
      title: 'Artikel',
      type: 'array',
      of: [{type: 'reference', to: [{type: 'artikel'}]}],
    }),
    defineField({
      name: 'personen',
      title: 'Personen',
      type: 'array',
      of: [{type: 'reference', to: [{type: 'person'}]}],
    }),
    defineField({
      name: 'reihenfolge',
      title: 'Reihenfolge',
      type: 'number',
      description: 'Bestimmt die Nummer auf der Karte (①, ②, …). Leer = am Ende.',
    }),
  ],
  orderings: [{title: 'Reihenfolge', name: 'reihenfolge', by: [{field: 'reihenfolge', direction: 'asc'}]}],
  preview: {select: {title: 'name', subtitle: 'adresse', media: 'bild'}},
})
