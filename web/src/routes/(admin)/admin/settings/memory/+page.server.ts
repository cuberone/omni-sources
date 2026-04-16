import { fail } from '@sveltejs/kit'
import { requireAdmin } from '$lib/server/authHelpers'
import { getConfigValue, setConfigValue } from '$lib/server/db/configuration'
import type { PageServerLoad, Actions } from './$types'

const VALID_MODES = ['off', 'chat', 'full']

export const load: PageServerLoad = async ({ locals }) => {
    requireAdmin(locals)

    const orgDefaultConfig = await getConfigValue('memory_mode_default')
    const orgDefault = (orgDefaultConfig?.value as string) ?? 'off'

    return { orgDefault }
}

export const actions: Actions = {
    default: async ({ request, locals }) => {
        requireAdmin(locals)

        const formData = await request.formData()
        const mode = formData.get('mode') as string

        if (!VALID_MODES.includes(mode)) {
            return fail(400, { error: 'Invalid memory mode' })
        }

        try {
            await setConfigValue('memory_mode_default', { value: mode })
            return { success: true }
        } catch (err) {
            console.error('Failed to update memory mode default:', err)
            return fail(500, { error: 'Failed to save default' })
        }
    },
}
