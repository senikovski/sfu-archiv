import {defineCliConfig} from 'sanity/cli'
import project from './project.json'

export default defineCliConfig({
  api: {projectId: project.projectId, dataset: project.dataset},
  studioHost: project.studioHost,
  deployment: {appId: project.appId},
})
