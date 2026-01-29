package io.github.dandriscoll.devlogs;

import hudson.Extension;
import hudson.model.Job;
import hudson.model.Run;
import jenkins.model.OptionalJobProperty;
import com.cloudbees.plugins.credentials.CredentialsProvider;
import org.jenkinsci.plugins.plaincredentials.StringCredentials;
import org.kohsuke.stapler.DataBoundConstructor;
import org.kohsuke.stapler.DataBoundSetter;

import java.util.logging.Level;
import java.util.logging.Logger;

/**
 * Job property that enables Devlogs log streaming for a pipeline job.
 *
 * Usage in Declarative Pipeline:
 * <pre>
 * pipeline {
 *     options {
 *         devlogs(credentialsId: 'devlogs')
 *     }
 *     stages { ... }
 * }
 * </pre>
 */
public class DevlogsJobProperty extends OptionalJobProperty<Job<?, ?>> {
    private static final Logger LOGGER = Logger.getLogger(DevlogsJobProperty.class.getName());

    private String credentialsId;
    private String application;
    private String component = "jenkins";
    private String environment;

    @DataBoundConstructor
    public DevlogsJobProperty(String credentialsId) {
        this.credentialsId = credentialsId;
    }

    public String getCredentialsId() {
        return credentialsId;
    }

    public String getApplication() {
        return application;
    }

    @DataBoundSetter
    public void setApplication(String application) {
        this.application = application;
    }

    public String getComponent() {
        return component;
    }

    @DataBoundSetter
    public void setComponent(String component) {
        this.component = component;
    }

    public String getEnvironment() {
        return environment;
    }

    @DataBoundSetter
    public void setEnvironment(String environment) {
        this.environment = environment;
    }

    /**
     * Resolve the URL from credentials for a given build.
     */
    public String resolveUrl(Run<?, ?> run) {
        if (credentialsId == null || credentialsId.trim().isEmpty()) {
            return null;
        }

        StringCredentials creds = CredentialsProvider.findCredentialById(
            credentialsId,
            StringCredentials.class,
            run
        );

        if (creds != null) {
            return creds.getSecret().getPlainText();
        }

        LOGGER.log(Level.WARNING, "Devlogs credentials not found: " + credentialsId);
        return null;
    }

    /**
     * Get the effective application name for a build.
     */
    public String getEffectiveApplication(Run<?, ?> run) {
        if (application != null && !application.trim().isEmpty()) {
            return application;
        }
        return run.getParent().getFullName();
    }

    @Extension
    public static class DescriptorImpl extends OptionalJobPropertyDescriptor {
        @Override
        public String getDisplayName() {
            return "Stream logs to Devlogs";
        }
    }
}
