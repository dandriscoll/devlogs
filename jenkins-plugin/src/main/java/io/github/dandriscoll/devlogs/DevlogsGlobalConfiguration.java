package io.github.dandriscoll.devlogs;

import com.cloudbees.plugins.credentials.CredentialsProvider;
import hudson.Extension;
import hudson.model.Run;
import jenkins.model.GlobalConfiguration;
import net.sf.json.JSONObject;
import org.jenkinsci.plugins.plaincredentials.StringCredentials;
import org.kohsuke.stapler.DataBoundSetter;
import org.kohsuke.stapler.StaplerRequest;

import java.util.logging.Level;
import java.util.logging.Logger;

/**
 * Global configuration for Devlogs plugin.
 * Configure via: Manage Jenkins → System → Devlogs
 */
@Extension
public class DevlogsGlobalConfiguration extends GlobalConfiguration {
    private static final Logger LOGGER = Logger.getLogger(DevlogsGlobalConfiguration.class.getName());

    private String credentialsId;
    private String application;
    private String component = "jenkins";
    private String environment;
    private boolean enabled = false;

    public DevlogsGlobalConfiguration() {
        load();
    }

    public static DevlogsGlobalConfiguration get() {
        return GlobalConfiguration.all().get(DevlogsGlobalConfiguration.class);
    }

    public String getCredentialsId() {
        return credentialsId;
    }

    @DataBoundSetter
    public void setCredentialsId(String credentialsId) {
        this.credentialsId = credentialsId;
        save();
    }

    public String getApplication() {
        return application;
    }

    @DataBoundSetter
    public void setApplication(String application) {
        this.application = application;
        save();
    }

    public String getComponent() {
        return component;
    }

    @DataBoundSetter
    public void setComponent(String component) {
        this.component = component;
        save();
    }

    public String getEnvironment() {
        return environment;
    }

    @DataBoundSetter
    public void setEnvironment(String environment) {
        this.environment = environment;
        save();
    }

    public boolean isEnabled() {
        return enabled;
    }

    @DataBoundSetter
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
        save();
    }

    @Override
    public boolean configure(StaplerRequest req, JSONObject json) throws FormException {
        req.bindJSON(this, json);
        save();
        return true;
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
}
