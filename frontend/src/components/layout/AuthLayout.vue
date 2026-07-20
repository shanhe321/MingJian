<script setup>
import rsodLogo from '@/assets/images/rsod-logo.png'
</script>

<template>
  <div class="auth-layout">
    <aside class="auth-visual">
      <img src="/teaser.png" alt="PCB 缺陷检测平台" class="auth-visual__image" />
      <div class="auth-visual__overlay">
        <div class="auth-visual__content">
          <span class="auth-visual__logo">
            <img :src="rsodLogo" alt="PCB 检测标识" />
          </span>
          <h1>PCB Defect Detection Platform</h1>
          <p>基于 YOLOv11 的目标检测智能体平台</p>
        </div>
      </div>
    </aside>

    <main class="auth-panel">
      <div class="auth-panel__inner">
        <slot />
      </div>
    </main>
  </div>
</template>

<style lang="scss" scoped>
.auth-layout {
  display: flex;
  width: 100%;
  min-height: 100vh;
  background: #f7fbff;
}

.auth-visual {
  position: relative;
  flex: 1;
  min-height: 100vh;
  overflow: hidden;
  background: #eef6fd;

  &__image {
    width: 100%;
    height: 100%;
    object-fit: cover;
    object-position: center;
    opacity: 0.72;
  }

  &__overlay {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: flex-end;
    padding: 48px;
    background: rgba(238, 246, 253, 0.2);
  }

  &__content {
    max-width: 420px;
    padding: 24px;
    border: 1px solid rgba(191, 216, 244, 0.82);
    border-radius: 20px;
    background: rgba(255, 255, 255, 0.9);
    color: $text-primary;

    h1 {
      font-size: 28px;
      font-weight: 600;
      line-height: 1.3;
      margin-bottom: 12px;
    }

    p {
      font-size: 15px;
      line-height: 1.6;
      color: $text-secondary;
    }
  }

  &__logo {
    display: inline-grid;
    place-items: center;
    width: 48px;
    height: 48px;
    overflow: hidden;
    margin-bottom: 20px;
    border: 1px solid $border-color;
    border-radius: 14px;
    background: #fff;

    img {
      width: 46px;
      height: 46px;
      max-width: none;
      object-fit: cover;
      transform: translateX(-3%) scale(1.55);
    }
  }
}

.auth-panel {
  flex: 0 0 480px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 48px 40px;
  border-left: 1px solid $border-color;
  background: #f7fbff;

  &__inner {
    width: 100%;
    max-width: 380px;
    padding: 36px;
    border: 1px solid $border-color;
    border-radius: $border-radius-lg;
    background: #fff;
    box-shadow: $shadow-lg;
    box-sizing: border-box;
  }
}

@media (max-width: 960px) {
  .auth-layout {
    flex-direction: column;
  }

  .auth-visual {
    flex: none;
    min-height: 240px;
    max-height: 320px;

    &__overlay {
      padding: 24px 32px;
    }

    &__content {
      h1 {
        font-size: 22px;
      }

      p {
        font-size: 13px;
      }
    }

    &__logo {
      margin-bottom: 12px;
    }
  }

  .auth-panel {
    flex: 1;
    padding: 32px 24px 48px;
    border-left: 0;
  }
}

@media (max-width: 520px) {
  .auth-visual {
    min-height: 190px;
    max-height: 220px;

    &__content {
      padding: 18px;
    }
  }

  .auth-panel {
    padding: 24px 16px 36px;

    &__inner {
      padding: 28px 22px;
    }
  }
}
</style>
