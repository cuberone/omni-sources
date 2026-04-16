<script lang="ts">
    import { enhance } from '$app/forms'
    import { Button } from '$lib/components/ui/button'
    import * as Card from '$lib/components/ui/card'
    import * as RadioGroup from '$lib/components/ui/radio-group'
    import { Label } from '$lib/components/ui/label'
    import type { PageProps } from './$types'

    let { data, form }: PageProps = $props()

    let selectedMode = $state(data.orgDefault)
    let isSubmitting = $state(false)

    const options = [
        {
            value: 'off',
            label: 'Off',
            description: 'Memory is disabled by default for all users.',
        },
        {
            value: 'chat',
            label: 'Chat memory',
            description: 'All users get chat memory by default.',
        },
        {
            value: 'full',
            label: 'Full memory',
            description: 'Chat memory plus agent run context for all users by default.',
        },
    ]
</script>

<svelte:head>
    <title>Memory - Settings - Admin</title>
</svelte:head>

<div class="h-full overflow-y-auto p-6 py-8 pb-24">
    <div class="mx-auto max-w-screen-lg space-y-8">
        <div>
            <h1 class="text-3xl font-bold tracking-tight">Memory</h1>
            <p class="text-muted-foreground mt-2">
                Set the organization-wide default memory mode. Users can override this in their
                personal preferences.
            </p>
        </div>

        <Card.Root>
            <Card.Header>
                <Card.Title>Default memory mode</Card.Title>
                <Card.Description>
                    This setting applies to all users who have not set a personal preference.
                </Card.Description>
            </Card.Header>
            <Card.Content>
                <form
                    method="POST"
                    use:enhance={() => {
                        isSubmitting = true
                        return async ({ update }) => {
                            isSubmitting = false
                            await update()
                        }
                    }}>
                    <input type="hidden" name="mode" value={selectedMode} />

                    <RadioGroup.Root
                        value={selectedMode}
                        onValueChange={(v) => {
                            selectedMode = v
                        }}
                        class="space-y-3">
                        {#each options as option}
                            {@const selected = selectedMode === option.value}
                            <Label
                                for={`mode-${option.value}`}
                                class="flex cursor-pointer items-start gap-3 rounded-md border p-4 transition-colors
                                    {selected
                                    ? 'border-blue-400/50 bg-blue-50/50 dark:border-blue-500/30 dark:bg-blue-950/20'
                                    : 'border-input hover:bg-accent/50'}">
                                <RadioGroup.Item
                                    value={option.value}
                                    id={`mode-${option.value}`}
                                    class="mt-0.5 shrink-0" />
                                <div>
                                    <p class="text-sm font-medium">{option.label}</p>
                                    <p class="text-muted-foreground text-sm">{option.description}</p>
                                </div>
                            </Label>
                        {/each}
                    </RadioGroup.Root>

                    {#if form?.error}
                        <p class="mt-4 text-sm text-red-500">{form.error}</p>
                    {/if}

                    {#if form?.success}
                        <p class="text-muted-foreground mt-4 text-sm">Default saved.</p>
                    {/if}

                    <div class="mt-6 space-y-3">
                        <Button type="submit" disabled={isSubmitting} class="cursor-pointer">
                            {isSubmitting ? 'Saving...' : 'Save default'}
                        </Button>
                        <p class="text-muted-foreground text-sm">
                            Users can override this in their personal preferences.
                        </p>
                    </div>
                </form>
            </Card.Content>
        </Card.Root>
    </div>
</div>
